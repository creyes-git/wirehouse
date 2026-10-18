"""Infrastructure and configuration: compose, Dockerfiles, env templates,
Terraform, Kubernetes, CI workflows, gateways and hosting platforms.

Secret hygiene: only env *templates* are read, and values are never copied
into the output. Values are used to infer a target (a database file name, a
host, a compose service), and only that derived label is kept.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from wirehouse.scan import ScanResult, as_dict, as_list

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class EnvVar:
    name: str
    value: str  # in memory only, never written out
    file: str
    line: int
    service: str | None = None  # compose service that sets it, if any
    commented: bool = False


@dataclass
class ComposeService:
    name: str
    file: str
    line: int
    image: str = ""
    build_context: str | None = None
    dockerfile: str | None = None
    command: str = ""
    ports: list[int] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    routed_by: list[str] = field(default_factory=list)   # "traefik" when its labels enable a router


@dataclass
class Dockerfile:
    rel: str
    cmd: str = ""
    expose: list[int] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    base: str = ""


@dataclass
class InfraItem:
    group: str          # terraform | kubernetes | ci | platform | gateway
    name: str
    kind: str           # warehouse kind for the leaf
    file: str
    line: int
    detail: str = ""
    targets: list[str] = field(default_factory=list)  # hostnames it points to (gateway)
    image: str = ""


@dataclass
class Infra:
    compose: list[ComposeService] = field(default_factory=list)
    dockerfiles: dict[str, Dockerfile] = field(default_factory=dict)
    env: list[EnvVar] = field(default_factory=list)
    items: list[InfraItem] = field(default_factory=list)


# YAML aliases share one object, so an 11-line file can describe a list of billions of items that only
# explodes when it is turned into text. Values are taken only when they are plain scalars, and capped.
MAX_VALUE = 1000
MAX_ITEMS = 200


def _scalar(value) -> str:
    """A YAML scalar as text, or "" for lists, mappings and anything else that could expand."""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)[:MAX_VALUE] if isinstance(value, (str, int, float)) else ""


def _scalars(value) -> list[str]:
    return [t for v in as_list(value)[:MAX_ITEMS] if (t := _scalar(v))]


def _line_of(text: str, needle: str, start: int = 0) -> int:
    i = text.find(needle, start)
    return text.count("\n", 0, i) + 1 if i >= 0 else 1


def _join(base: str, rel: str) -> str:
    parts = (base.split("/") if base else []) + rel.replace("\\", "/").split("/")
    out: list[str] = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p and p != ".":
            out.append(p)
    return "/".join(out)


def _ports(raw) -> list[int]:
    out = []
    for p in as_list(raw)[:MAX_ITEMS]:
        s = _scalar(p.get("target") if isinstance(p, dict) else p)
        nums = re.findall(r"\d{2,5}", s.split("/")[0])
        if nums:
            out.append(int(nums[-1]))
    return out


def _parse_compose(scan: ScanResult, rel: str, infra: Infra) -> None:
    if yaml is None:
        return
    text = scan.read(rel)
    try:
        data = as_dict(yaml.safe_load(text))
    except yaml.YAMLError:
        return
    base = rel.rsplit("/", 1)[0] if "/" in rel else ""
    for name, svc in as_dict(data.get("services")).items():
        if not isinstance(svc, dict):
            continue
        cs = ComposeService(name=name, file=rel, line=_line_of(text, f"\n  {name}:") + 1 if f"\n  {name}:" in text else _line_of(text, f"{name}:"))
        cs.image = _scalar(svc.get("image") or "")
        b = svc.get("build")
        if isinstance(b, str):
            cs.build_context = _join(base, b)
        elif isinstance(b, dict):
            cs.build_context = _join(base, _scalar(b.get("context", ".")))
            if _scalar(b.get("dockerfile")):
                cs.dockerfile = _join(cs.build_context, _scalar(b["dockerfile"]))
        if cs.build_context is not None and cs.dockerfile is None:
            cs.dockerfile = _join(cs.build_context, "Dockerfile")
        cmd = svc.get("command") or svc.get("entrypoint") or ""
        cs.command = " ".join(_scalars(cmd)) if isinstance(cmd, list) else _scalar(cmd)
        cs.ports = _ports(svc.get("ports")) + _ports(svc.get("expose"))
        dep = svc.get("depends_on") or []
        cs.depends_on = _scalars(list(dep.keys()) if isinstance(dep, dict) else dep)
        env = svc.get("environment") or {}
        if isinstance(env, list):
            env = dict(e.split("=", 1) if "=" in e else (e, "") for e in _scalars(env))
        cs.env = {_scalar(k): _scalar(v) for k, v in list(as_dict(env).items())[:MAX_ITEMS] if _scalar(k)}
        labels = svc.get("labels") or {}
        if isinstance(labels, dict):
            values = {_scalar(k): _scalar(v) for k, v in list(labels.items())[:MAX_ITEMS]}
        else:
            values = dict(x.split("=", 1) if "=" in x else (x, "") for x in _scalars(labels))
        keys = list(values)
        if values.get("traefik.enable", "").lower() == "true" or any(k.startswith("traefik.http.routers.") for k in keys):
            cs.routed_by.append("traefik")
        for k, v in cs.env.items():
            infra.env.append(EnvVar(k, v, rel, _line_of(text, k), service=name))
        infra.compose.append(cs)


def _parse_dockerfile(scan: ScanResult, rel: str, infra: Infra) -> None:
    text = scan.read(rel)
    df = Dockerfile(rel=rel)
    joined = re.sub(r"\\\r?\n", " ", text)
    for raw in joined.splitlines():
        s = raw.strip()
        up = s.upper()
        if up.startswith("FROM "):
            words = [w for w in s.split()[1:] if not w.startswith("--")]   # FROM --platform=linux/amd64 python:3.12
            df.base = words[0] if words else ""
        elif up.startswith(("CMD ", "ENTRYPOINT ")):
            body = s.split(None, 1)[1] if " " in s else ""
            try:
                parsed = json.loads(body)
                body = " ".join(map(str, parsed)) if isinstance(parsed, list) else body
            except ValueError:
                pass
            df.cmd = (df.cmd + " " + body).strip() if up.startswith("CMD") and df.cmd else body
        elif up.startswith("EXPOSE "):
            df.expose += [int(p) for p in re.findall(r"\d{2,5}", s)]
        elif up.startswith("ENV "):
            for m in re.finditer(r"(\w+)[= ]([^\s]+)", s[4:]):
                df.env[m.group(1)] = m.group(2)
    for k, v in df.env.items():
        infra.env.append(EnvVar(k, v, rel, _line_of(text, k)))
    infra.dockerfiles[rel] = df


def _parse_env_template(scan: ScanResult, rel: str, infra: Infra) -> None:
    text = scan.read(rel)
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        commented = s.startswith("#")
        if commented:
            s = s.lstrip("#").strip()
        m = re.match(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*)$", s)
        if m:
            infra.env.append(EnvVar(m.group(1), m.group(2).strip().strip("'\""), rel, i, commented=commented))


def _parse_appsettings(scan: ScanResult, rel: str, infra: Infra) -> None:
    text = scan.read(rel)
    try:
        data = as_dict(json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.M)))
    except ValueError:
        return
    for k, v in as_dict(data.get("ConnectionStrings")).items():
        infra.env.append(EnvVar(k, str(v), rel, _line_of(text, f'"{k}"')))
        infra.env.append(EnvVar(f"ConnectionStrings:{k}", str(v), rel, _line_of(text, f'"{k}"')))


TF_KIND = [
    (r"(db_instance|rds_cluster|sql_server|sql_database|postgresql|mysql|cosmosdb|sql_database_instance|spanner|dynamodb)", "database"),
    (r"(elasticache|redis|memorystore)", "cache"),
    (r"(sqs|sns|servicebus|pubsub|eventhub|kinesis|eventgrid|mq_broker)", "queue"),
    (r"(s3_bucket|storage_account|storage_bucket|storage_container|efs)", "storage"),
    (r"(cognito|active_directory|identity|iam_openid)", "auth"),
    (r"(api_gateway|apigatewayv2|lb|alb|application_gateway|cdn|cloudfront|front_door)", "gateway"),
    (r"(lambda_function|function_app|cloudfunctions)", "function"),
    (r"(ecs_service|ecs_task|instance|app_service|linux_web_app|windows_web_app|container_app|cloud_run|kubernetes_cluster|eks|aks|container_group|app_runner)", "service"),
]


def _parse_terraform(scan: ScanResult, rel: str, infra: Infra) -> None:
    text = scan.read(rel)
    for m in re.finditer(r'^\s*resource\s+"(\w+)"\s+"([\w-]+)"', text, re.M):
        rtype, rname = m.group(1), m.group(2)
        kind = "infra"
        for pat, k in TF_KIND:
            if re.search(pat, rtype):
                kind = k
                break
        infra.items.append(InfraItem("terraform", f"{rname} ({rtype})", kind, rel, text.count("\n", 0, m.start()) + 1, detail=rtype))


def _parse_k8s(scan: ScanResult, rel: str, infra: Infra) -> None:
    if yaml is None:
        return
    text = scan.read(rel)
    if "apiVersion" not in text or "kind" not in text:
        return
    try:
        docs = list(yaml.safe_load_all(text))
    except yaml.YAMLError:
        return
    for d in docs:
        if not isinstance(d, dict) or "kind" not in d:
            continue
        kind = _scalar(d.get("kind")) or "Unknown"
        name = _scalar(as_dict(d.get("metadata")).get("name")) or kind
        image = ""
        try:
            tpl = d["spec"].get("template", {}).get("spec", {}) if kind != "CronJob" else d["spec"]["jobTemplate"]["spec"]["template"]["spec"]
            image = _scalar(((tpl.get("containers") or [{}])[0]).get("image") or "")
        except (KeyError, AttributeError, TypeError):
            pass
        wk = {"Ingress": "gateway", "Service": "infra", "Deployment": "service", "StatefulSet": "database",
              "CronJob": "worker", "Job": "worker", "DaemonSet": "service"}.get(kind, "infra")
        infra.items.append(InfraItem("kubernetes", f"{name} ({kind})", wk, rel, _line_of(text, f"name: {name}"), detail=kind, image=image))


DEPLOY_HINTS = [
    ("vercel", "Vercel"), ("netlify", "Netlify"), ("fly", "Fly.io"), ("azure/webapps-deploy", "Azure App Service"),
    ("azure/functions-action", "Azure Functions"), ("aws-actions", "AWS"), ("google-github-actions", "Google Cloud"),
    ("docker/build-push-action", "Docker registry"), ("peaceiris/actions-gh-pages", "GitHub Pages"),
    ("railway", "Railway"), ("render", "Render"), ("heroku", "Heroku"), ("cloudflare/wrangler-action", "Cloudflare"),
]


def _parse_workflow(scan: ScanResult, rel: str, infra: Infra) -> None:
    text = scan.read(rel)
    name = rel.rsplit("/", 1)[-1]
    jobs: list[str] = []
    triggers = ""
    if yaml is not None:
        try:
            data = as_dict(yaml.safe_load(text))
            name = _scalar(data.get("name")) or name
            jobs = _scalars(list(as_dict(data.get("jobs"))))
            on = data.get(True) or data.get("on") or {}
            triggers = ", ".join(_scalars(list(on) if isinstance(on, dict) else on)) if isinstance(on, (dict, list)) else _scalar(on)
        except yaml.YAMLError:
            pass
    # whole words only: test_renderer.py is not Render, --project=firefly is not Fly.io
    deploys = sorted({label for hint, label in DEPLOY_HINTS if re.search(rf"(?<![\w-]){re.escape(hint)}(?![\w-])", text.lower())})
    detail = f"Triggers: {triggers or 'unknown'}. Jobs: {', '.join(jobs) or 'n/a'}."
    if deploys:
        detail += f" Deploys to: {', '.join(deploys)}."
    infra.items.append(InfraItem("ci", name, "ci", rel, 1, detail=detail))


PLATFORMS = {
    "vercel.json": "Vercel", "netlify.toml": "Netlify", "fly.toml": "Fly.io", "render.yaml": "Render",
    "railway.json": "Railway", "railway.toml": "Railway", "app.yaml": "Google App Engine", "serverless.yml": "Serverless Framework",
    "serverless.yaml": "Serverless Framework", "firebase.json": "Firebase Hosting", "wrangler.toml": "Cloudflare Workers", "procfile": "Heroku",
}


def _parse_gateway(scan: ScanResult, rel: str, infra: Infra) -> None:
    text = scan.read(rel)
    targets = re.findall(r"(?:proxy_pass|reverse_proxy|url:)\s+(?:https?://)?([A-Za-z0-9_.-]+)(?::\d+)?", text)
    low = rel.lower()
    label = "Nginx" if "nginx" in low else "Caddy" if "caddy" in low else "Traefik"
    infra.items.append(InfraItem("gateway", label, "gateway", rel, 1, detail=f"Routes to: {', '.join(sorted(set(targets))) or 'n/a'}",
                                 targets=sorted(set(targets))))


def _compose_rank(rel: str) -> tuple:
    name = rel.rsplit("/", 1)[-1].lower()
    return (rel.count("/"), "override" in name, name not in ("compose.yml", "compose.yaml", "docker-compose.yml", "docker-compose.yaml"), rel)


def _merge_compose(services: list[ComposeService]) -> list[ComposeService]:
    """Services with the same name in the same folder are one service spread over several files
    (compose.yml + compose.override.yml): merge them, the base file first, as Compose does."""
    merged: dict[tuple[str, str], ComposeService] = {}
    for cs in services:
        key = (cs.file.rsplit("/", 1)[0] if "/" in cs.file else "", cs.name)
        m = merged.get(key)
        if m is None:
            merged[key] = cs
            continue
        m.image = cs.image or m.image
        if cs.build_context is not None:
            m.build_context, m.dockerfile = cs.build_context, cs.dockerfile or m.dockerfile
        m.command = cs.command or m.command
        m.ports = list(dict.fromkeys(m.ports + cs.ports))
        m.depends_on = list(dict.fromkeys(m.depends_on + cs.depends_on))
        m.env = {**m.env, **cs.env}
        m.routed_by = list(dict.fromkeys(m.routed_by + cs.routed_by))
    return list(merged.values())


def detect_infra(scan: ScanResult) -> Infra:
    infra = Infra()
    for rel in sorted(scan.configs.get("compose", []), key=_compose_rank):
        _parse_compose(scan, rel, infra)
    infra.compose = _merge_compose(infra.compose)
    for rel in scan.configs.get("dockerfile", []):
        _parse_dockerfile(scan, rel, infra)
    # Compose may point at a Dockerfile the scan skipped (unusual names).
    for cs in infra.compose:
        if cs.dockerfile and cs.dockerfile not in infra.dockerfiles and (scan.root / cs.dockerfile).is_file():
            _parse_dockerfile(scan, cs.dockerfile, infra)
    for rel in scan.configs.get("env_template", []):
        _parse_env_template(scan, rel, infra)
    for rel in scan.configs.get("appsettings", []):
        _parse_appsettings(scan, rel, infra)
    for rel in scan.configs.get("terraform", []):
        _parse_terraform(scan, rel, infra)
    for rel in scan.configs.get("k8s", []):
        _parse_k8s(scan, rel, infra)
    for rel in scan.configs.get("workflow", []):
        _parse_workflow(scan, rel, infra)
    for rel in scan.configs.get("gateway_config", []):
        _parse_gateway(scan, rel, infra)
    for rel in scan.configs.get("platform", []):
        fname = rel.rsplit("/", 1)[-1].lower()
        label = PLATFORMS.get(fname)
        if label:
            infra.items.append(InfraItem("platform", label, "infra", rel, 1, detail=f"Hosting config in {rel}"))
    return infra
