"""End-to-end checks on a small but realistic fixture repo."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from wirehouse.build import build_archmap
from wirehouse.enrich import merge, nodes_needing_text, write_brief
from wirehouse.render.html import render_html

SECRET = "sk_live_DO_NOT_LEAK_42"

FILES = {
    "docker-compose.yml": """
        services:
          web:
            build: ./web
            environment:
              API_URL: http://api:8000
            ports: ["3000:3000"]
            depends_on: [api]
          api:
            build: ./api
            command: uvicorn main:app --host 0.0.0.0 --port 8000
            environment:
              DATABASE_URL: postgresql://app:pw@db:5432/app
              REDIS_URL: redis://cache:6379/0
            depends_on: [db, cache]
          db:
            image: postgres:16
          cache:
            image: redis:7-alpine
    """,
    ".env.example": f"""
        STRIPE_SECRET_KEY={SECRET}
        # OPENAI_API_KEY=
    """,
    ".env": "REAL_SECRET=hunter2_never_read\n",
    ".github/workflows/ci.yml": """
        name: CI
        on: [push]
        jobs:
          test:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
    """,
    "web/package.json": json.dumps({
        "name": "shop-web",
        "dependencies": {"next": "15.0.0", "react": "19.0.0", "react-dom": "19.0.0", "@clerk/nextjs": "6.0.0", "stripe": "17.0.0"},
    }),
    # JSONC with a comment and a glob that looks like a comment opener: both must parse
    "web/tsconfig.json": '{\n  // aliases\n  "compilerOptions": {"paths": {"@/*": ["./*"]}},\n  "include": ["**/*.ts", "**/*.tsx",],\n}\n',
    "web/app/page.tsx": "export default function Home() { return null }\n",
    "web/app/api/orders/route.ts": """
        import { apiFetch } from "@/lib/api";
        export async function GET() { return apiFetch("/orders"); }
        export async function POST() { return apiFetch("/orders", { method: "POST" }); }
    """,
    "web/lib/api.ts": """
        /** Talks to the Python API. */
        export async function apiFetch(path: string, init?: RequestInit) {
          return fetch(`${process.env.API_URL}${path}`, init);
        }
    """,
    "web/lib/payments.ts": """
        import Stripe from "stripe";
        export const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);
    """,
    "web/middleware.ts": """
        import { clerkMiddleware } from "@clerk/nextjs/server";
        export default clerkMiddleware();
    """,
    "api/requirements.txt": "fastapi>=0.110\nsqlalchemy>=2\npsycopg2-binary\nredis>=5\n",
    "api/main.py": '''
        """Orders API."""
        from fastapi import FastAPI
        from routers import orders

        app = FastAPI()
        app.include_router(orders.router)

        @app.get("/health")
        def health():
            return {"ok": True}
    ''',
    "api/routers/__init__.py": "",
    "api/routers/orders.py": """
        from fastapi import APIRouter
        from db import SessionLocal
        from models import Order

        router = APIRouter(prefix="/orders")

        @router.get("")
        def list_orders():
            return []

        @router.post("/{order_id}/pay")
        def pay(order_id: int):
            return {}
    """,
    "api/db.py": """
        import os
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(os.environ["DATABASE_URL"])
        SessionLocal = sessionmaker(bind=engine)
    """,
    "api/models.py": """
        from sqlalchemy.orm import DeclarativeBase

        class Base(DeclarativeBase):
            pass

        class Order(Base):
            __tablename__ = "orders"
    """,
    "api/cache.py": """
        import os
        import redis
        client = redis.from_url(os.getenv("REDIS_URL"))
    """,
    "api/tests/test_orders.py": "import duckdb\n",
}


@pytest.fixture(scope="module")
def repo(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("shop")
    for rel, body in FILES.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def archmap(repo) -> dict:
    return build_archmap(repo, log=lambda *_: None)


def _index(data):
    nodes = {n["id"]: n for n in data["nodes"]}

    def top(i):
        while nodes[i]["parent"]:
            i = nodes[i]["parent"]
        return i

    links = {(top(e["source"]), top(e["target"]), e["kind"]) for e in data["edges"] if top(e["source"]) != top(e["target"])}
    return nodes, links


def test_units_are_classified(archmap):
    nodes, _ = _index(archmap)
    assert nodes["unit:js:web"]["kind"] == "frontend"
    assert nodes["unit:js:web"]["framework"] == "Next.js"
    assert nodes["unit:python:api"]["kind"] == "service"
    assert nodes["unit:python:api"]["compose"] == ["api"]
    assert 8000 in nodes["unit:python:api"]["ports"]


def test_resources_and_layers(archmap):
    nodes, _ = _index(archmap)
    assert nodes["res:postgres"]["layer"] == "data"
    assert nodes["res:redis"]["kind"] == "cache"
    assert nodes["res:stripe"]["layer"] == "external"
    assert nodes["res:clerk"]["layer"] == "edge"
    assert nodes["infra:ci"]["layer"] == "ops"
    # test-only imports must not create blocks
    assert not any(i.startswith("res:duckdb") for i in nodes)


def test_connections_roll_up(archmap):
    _, links = _index(archmap)
    assert ("unit:js:web", "unit:python:api", "calls") in links          # API_URL -> compose service api
    assert ("unit:python:api", "res:postgres", "data") in links           # DATABASE_URL -> compose db (postgres image)
    assert ("unit:python:api", "res:redis", "data") in links
    assert ("unit:js:web", "res:stripe", "calls") in links
    assert ("unit:js:web", "res:clerk", "auth") in links
    assert ("actor:users", "unit:js:web", "calls") in links
    # depends_on is dropped where a real connection already explains the pair
    assert ("unit:js:web", "unit:python:api", "depends_on") not in links


def test_files_tables_and_endpoints(archmap):
    nodes, _ = _index(archmap)
    route = nodes["file:web/app/api/orders/route.ts"]
    assert {(e["method"], e["path"]) for e in route["endpoints"]} == {("GET", "/api/orders"), ("POST", "/api/orders")}
    orders = nodes["file:api/routers/orders.py"]
    assert {(e["method"], e["path"]) for e in orders["endpoints"]} == {("GET", "/orders"), ("POST", "/orders/{order_id}/pay")}
    assert nodes["table:postgres:orders"]["parent"] == "res:postgres"
    assert nodes["file:web/lib/api.ts"]["doc"] == "Talks to the Python API."
    imports = {(e["source"], e["target"]) for e in archmap["edges"] if e["kind"] == "imports"}
    assert ("file:web/app/api/orders/route.ts", "file:web/lib/api.ts") in imports   # tsconfig "@/*" alias
    assert ("file:api/routers/orders.py", "file:api/db.py") in imports


def test_secrets_never_leak(repo, archmap):
    blob = json.dumps(archmap)
    assert SECRET not in blob
    assert "hunter2" not in blob
    assert "pw@db" not in blob
    assert SECRET not in render_html(archmap)


def test_enrichment_roundtrip(repo, archmap, tmp_path):
    data = json.loads(json.dumps(archmap))
    web = next(n for n in data["nodes"] if n["id"] == "unit:js:web")
    enrichment = {
        "nodes": {"unit:js:web": {"description": "The storefront.", "purpose": "Sells things.", "hash": web["hash"], "name": "Storefront"}},
        "links": {"unit:js:web->unit:python:api": {"description": "Order reads and writes."}},
        "add_nodes": [{"id": "res:sendgrid", "name": "SendGrid", "kind": "external"}],
        "add_edges": [{"source": "unit:python:api", "target": "res:sendgrid", "kind": "calls", "evidence": [{"file": "api/main.py", "line": 1}]}],
        "remove_nodes": ["infra:ci"],
    }
    pending_before = {n["id"] for n in nodes_needing_text(data, {})}
    assert "unit:js:web" in pending_before
    assert "unit:js:web" not in {n["id"] for n in nodes_needing_text(data, enrichment)}
    merged = merge(data, enrichment)
    nodes, links = _index(merged)
    assert nodes["unit:js:web"]["name"] == "Storefront"
    assert nodes["unit:js:web"]["purpose"] == "Sells things."
    assert ("unit:python:api", "res:sendgrid", "calls") in links
    assert "infra:ci" not in nodes
    assert merged["link_notes"]["unit:js:web->unit:python:api"] == "Order reads and writes."
    brief, n_nodes, _ = write_brief(archmap, enrichment, tmp_path)
    assert "`unit:js:web`" not in brief.read_text(encoding="utf-8")


def test_html_is_self_contained(archmap):
    html = render_html(archmap)
    assert "window.WIREHOUSE = " in html
    assert "/*__" not in html            # every placeholder was filled
    assert "<script src=" not in html    # nothing loaded from the network
    assert html.count("</script>") == 3


def test_dotnet_and_terraform(tmp_path):
    files = {
        "src/Shop.Api/Shop.Api.csproj": r"""
            <Project Sdk="Microsoft.NET.Sdk.Web">
              <ItemGroup>
                <PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="8.0.0" />
                <PackageReference Include="Microsoft.Identity.Web" Version="2.0.0" />
                <ProjectReference Include="..\Shop.Core\Shop.Core.csproj" />
              </ItemGroup>
            </Project>
        """,
        "src/Shop.Api/Controllers/OrdersController.cs": """
            using Microsoft.AspNetCore.Mvc;
            [ApiController]
            [Route("api/[controller]")]
            public class OrdersController : ControllerBase {
                [HttpGet] public IActionResult List() => Ok();
                [HttpPost("{id}/ship")] public IActionResult Ship(int id) => Ok();
            }
        """,
        "src/Shop.Api/Data/ShopDb.cs": """
            using Microsoft.EntityFrameworkCore;
            public class ShopDb : DbContext {
                public DbSet<Order> Orders { get; set; }
            }
        """,
        "src/Shop.Api/appsettings.json": '{"ConnectionStrings": {"Main": "Server=sql;Database=shop;User Id=sa;Password=NotThis1!"}}',
        "src/Shop.Core/Shop.Core.csproj": '<Project Sdk="Microsoft.NET.Sdk"></Project>',
        "src/Shop.Core/Order.cs": "public class Order { public int Id { get; set; } }",
        "infra/main.tf": 'resource "azurerm_mssql_database" "shop" {}\nresource "azurerm_linux_web_app" "api" {}\n',
    }
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    data = build_archmap(tmp_path, log=lambda *_: None)
    nodes, links = _index(data)
    api = nodes["unit:dotnet:src/Shop.Api"]
    assert api["kind"] == "service" and api["framework"] == "ASP.NET Core"
    assert nodes["unit:dotnet:src/Shop.Core"]["kind"] == "library"
    assert ("unit:dotnet:src/Shop.Api", "unit:dotnet:src/Shop.Core", "imports") in links
    assert ("unit:dotnet:src/Shop.Api", "res:sqlserver", "data") in links
    assert ("unit:dotnet:src/Shop.Api", "res:entra", "auth") in links
    eps = {(e["method"], e["path"]) for e in nodes["file:src/Shop.Api/Controllers/OrdersController.cs"]["endpoints"]}
    assert eps == {("GET", "/api/orders"), ("POST", "/api/orders/{id}/ship")}
    assert nodes["table:sqlserver:orders"]["parent"] == "res:sqlserver"
    tf = [n for n in data["nodes"] if n["parent"] == "infra:terraform"]
    assert {n["subkind"] for n in tf} == {"database", "service"}
    assert ("infra:terraform", "res:sqlserver", "provisions") in links
    assert "NotThis1!" not in json.dumps(data)


def test_url_mentions_do_not_create_blocks(tmp_path):
    # A provider URL in data (a catalog, a README-ish constant) is not a call: no block on the floor.
    files = {
        "app/package.json": json.dumps({"name": "app", "dependencies": {"express": "4.0.0"}}),
        "app/catalog.js": 'export const BRANDS = [{ id: "openrouter", site: "https://openrouter.ai" }];\n',
        "app/server.js": 'const r = await fetch("https://api.github.com/repos/x/y");\n',
    }
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    nodes, links = _index(build_archmap(tmp_path, log=lambda *_: None))
    assert "res:openrouter" not in nodes
    assert ("unit:js:app", "res:github", "calls") in links


def test_remote_parsing_strips_credentials():
    from wirehouse.repo import parse_remote

    gh = parse_remote("https://bot:ghp_SECRET123@github.com/acme/shop.git")
    assert gh == {"provider": "github", "web": "https://github.com/acme/shop"}
    assert parse_remote("git@github.com:acme/shop.git") == gh
    assert parse_remote("ssh://git@gitlab.example.com:2222/team/sub/shop.git") == {"provider": "gitlab", "web": "https://gitlab.example.com/team/sub/shop"}
    assert parse_remote("git@bitbucket.org:acme/shop.git")["provider"] == "bitbucket"
    assert parse_remote("https://acme@dev.azure.com/acme/Shop/_git/shop-api") == {"provider": "azure", "web": "https://dev.azure.com/acme/Shop/_git/shop-api"}
    assert parse_remote("git@ssh.dev.azure.com:v3/acme/Shop/shop-api") == {"provider": "azure", "web": "https://dev.azure.com/acme/Shop/_git/shop-api"}
    assert parse_remote("git@github-work:acme/shop.git") is None        # ssh config alias: unknown host
    assert parse_remote("https://git.internal.example/acme/shop") is None
    assert parse_remote("") is None


def test_repo_info_pins_commit_without_leaking_remote(tmp_path):
    import shutil
    import subprocess

    if not shutil.which("git"):
        pytest.skip("git not installed")
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "svc" / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    run = lambda *a: subprocess.run(["git", "-C", str(tmp_path), *a], check=True, capture_output=True)  # noqa: E731
    run("init", "-q")
    run("-c", "user.name=t", "-c", "user.email=t@example.com", "add", "-A")
    run("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "init")
    run("remote", "add", "origin", "https://bot:ghp_SECRET123@github.com/acme/shop.git")
    (tmp_path / "svc" / "main.py").write_text("print('changed')\n", encoding="utf-8")
    data = build_archmap(tmp_path / "svc", log=lambda *_: None)
    repo = data["repo"]
    assert repo["provider"] == "github" and repo["web"] == "https://github.com/acme/shop"
    assert len(repo["revision"]) == 40 and repo["prefix"] == "svc"
    assert repo["dirty"] == ["main.py"]
    assert repo["pushed"] is False
    assert "ghp_SECRET123" not in json.dumps(data)
    assert "ghp_SECRET123" not in render_html(data)


def test_tours_and_quests_are_checked(repo, archmap):
    from wirehouse import guide

    data = json.loads(json.dumps(archmap))
    enrichment = {
        "tours": [{"id": "pay", "title": "How an order gets paid", "stops": [
            {"node": "unit:js:web", "text": "The storefront takes the order.", "evidence": [{"file": "web/app/api/orders/route.ts", "line": 2}]},
            {"node": "file:web/lib/payments.ts", "text": f"Built with {SECRET}.", "evidence": [{"file": "web/lib/payments.ts", "line": 99}]},
            {"node": "res:nope", "text": "Ghost."},
            {"node": "res:stripe", "text": "Takes the money.", "evidence": [{"file": "../outside.txt", "line": 1}, {"file": "docker-compose.yml", "line": 3}]},
        ]}, {"title": "Broken", "route": ["actor:users", "res:missing"]}],
        "quests": [{"question": "Where is Stripe set up?", "answer": "file:web/lib/payments.ts"}, {"question": "Bad", "answer": ["res:ghost"]}],
    }
    data = guide.apply(merge(data, enrichment), enrichment)
    codes = {(d["code"], d["subject"]) for d in data["diagnostics"]}
    assert ("evidence/line-out-of-range", "tours[pay].stops[1]") in codes
    assert ("tour/unknown-node", "tours[pay].stops[2]") in codes
    assert ("evidence/file-not-found", "tours[pay].stops[3]") in codes
    assert ("guide/secret-like-text", "tours[pay].stops[1]") in codes
    assert ("tour/unknown-node", "tours[broken]") in codes
    assert ("quest/invalid", "quests[bad]") in codes
    [tour] = data["tours"]
    assert [s["node"] for s in tour["stops"]] == ["unit:js:web", "file:web/lib/payments.ts", "res:stripe"]
    assert tour["stops"][2]["evidence"] == [{"file": "docker-compose.yml", "line": 3}]   # non-source files are checked on disk
    assert [q["answer"] for q in data["quests"]] == [["file:web/lib/payments.ts"]]
    assert SECRET not in json.dumps(data) and SECRET not in render_html(data)


def test_enrichment_text_is_scanned_for_credentials(archmap):
    from wirehouse import guide

    web = next(n for n in archmap["nodes"] if n["id"] == "unit:js:web")
    enrichment = {"nodes": {"unit:js:web": {"description": f"Pays with {SECRET}.", "hash": web["hash"]}},
                  "links": {"unit:js:web->unit:python:api": {"description": "token=abcd1234efgh in the header"}}}
    data = guide.apply(merge(json.loads(json.dumps(archmap)), enrichment), enrichment)
    blob = json.dumps(data)
    assert SECRET not in blob and "abcd1234efgh" not in blob
    assert {d["code"] for d in data["diagnostics"]} == {"guide/secret-like-text"}


def test_wirehouse_makes_tours_and_quests_when_none_are_written(archmap):
    from wirehouse import guide

    data = guide.apply(json.loads(json.dumps(archmap)), {})
    tours = {t["id"]: t for t in data["tours"]}
    assert tours["main-floor"]["stops"][0]["node"] == "actor:users"          # entrance first
    assert tours["request"]["route"] == ["actor:users", "res:postgres"]
    quests = {q["id"]: q for q in data["quests"]}
    assert quests["find-endpoint"]["answer"] == ["file:api/routers/orders.py"]
    assert set(quests["find-data"]["answer"]) == {"res:postgres", "res:redis"}
    assert all(t["auto"] for t in data["tours"]) and data["diagnostics"] == []


SCHEMA_FILES = {
    "docker-compose.yml": """
        services:
          api:
            build: ./api
            environment:
              DATABASE_URL: postgresql://app:pw@db:5432/app
          db:
            image: postgres:16
    """,
    "api/requirements.txt": "sqlalchemy>=2\npsycopg2-binary\n",
    "api/db.py": "import os\nfrom sqlalchemy import create_engine\nengine = create_engine(os.environ['DATABASE_URL'])\n",
    "api/migrations/001_init.sql": """
        CREATE TABLE customers (
          id SERIAL PRIMARY KEY,
          email VARCHAR(255) NOT NULL UNIQUE,
          password_hash TEXT NOT NULL DEFAULT 'hunter2_default'
        );
        CREATE TABLE invoices (
          id BIGINT,
          customer_id INTEGER NOT NULL,
          total NUMERIC(10, 2),
          CONSTRAINT invoices_pk PRIMARY KEY (id),
          CONSTRAINT fk_cust FOREIGN KEY (customer_id) REFERENCES customers (id)
        );
    """,
    "api/models.py": """
        from sqlalchemy import ForeignKey, String
        from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

        class Base(DeclarativeBase):
            pass

        class Shipment(Base):
            __tablename__ = "shipments"
            id: Mapped[int] = mapped_column(primary_key=True)
            invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), nullable=False)
            carrier: Mapped[str] = mapped_column(String(40))
    """,
}


def test_schema_columns_and_foreign_keys(tmp_path):
    for rel, body in SCHEMA_FILES.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    data = build_archmap(tmp_path, log=lambda *_: None)
    nodes = {n["id"]: n for n in data["nodes"]}
    cols = {c["name"]: c for c in nodes["table:postgres:invoices"]["columns"]}
    assert cols["id"].get("pk") and cols["customer_id"]["fk"] == {"table": "customers", "column": "id"}
    assert cols["total"]["type"] == "NUMERIC(10, 2)" and cols["customer_id"].get("required")
    ship = {c["name"]: c for c in nodes["table:postgres:shipments"]["columns"]}
    assert ship["id"].get("pk") and ship["invoice_id"]["fk"] == {"table": "invoices", "column": "id"}
    refs = {(e["source"], e["target"]) for e in data["edges"] if e["kind"] == "references"}
    assert refs == {("table:postgres:invoices", "table:postgres:customers"), ("table:postgres:shipments", "table:postgres:invoices")}
    assert "hunter2_default" not in json.dumps(data)   # column defaults are never kept


def test_schema_dialects():
    from wirehouse.detectors import schema

    prisma = 'model User {\n  id Int @id @default(autoincrement())\n  posts Post[]\n}\nmodel Post {\n  id Int @id\n  authorId Int\n  author User @relation(fields: [authorId], references: [id])\n  title String?\n}\n'
    post = schema.prisma_columns(prisma, prisma.index("model Post"), {"User", "Post"})
    assert [c["name"] for c in post] == ["id", "authorId", "title"]
    assert post[1]["fk"] == {"table": "User", "column": "id"} and "required" not in post[2]

    django = "class Order(models.Model):\n    customer = models.ForeignKey('shop.Customer', on_delete=models.CASCADE)\n    total = models.DecimalField(max_digits=8)\n"
    dj = schema.django_columns(django, 0)
    assert [c["name"] for c in dj] == ["id", "customer_id", "total"] and dj[1]["fk"]["table"] == "Customer"

    drizzle = 'export const users = pgTable("users", { id: serial("id").primaryKey() });\nexport const posts = pgTable("posts", {\n  id: serial("id").primaryKey(),\n  authorId: integer("author_id").notNull().references(() => users.id),\n});\n'
    dz = schema.drizzle_columns(drizzle, drizzle.index("export const posts"), {"users": "users", "posts": "posts"})
    assert dz[1] == {"name": "author_id", "type": "integer", "fk": {"table": "users", "column": "id"}, "required": True}

    typeorm = "@Entity()\nexport class Photo {\n  @PrimaryGeneratedColumn()\n  id: number;\n  @Column()\n  url: string;\n  @ManyToOne(() => User)\n  owner: User;\n}\n"
    to = schema.typeorm_columns(typeorm, 0)
    assert [(c["name"], c.get("pk", False)) for c in to] == [("id", True), ("url", False), ("ownerId", False)]
    assert to[2]["fk"]["table"] == "User"


def test_template_style_repo(tmp_path):
    # Shaped like fastapi/full-stack-fastapi-template: services split over compose.yml and
    # compose.override.yml, a backend built from the repo root with backend/Dockerfile, Traefik
    # routing through labels, SQLModel tables and a React Email package.
    files = {
        "compose.yml": """
            services:
              proxy:
                image: traefik:v3.1
              db:
                image: postgres:17
              backend:
                image: backend:latest
                build:
                  context: .
                  dockerfile: backend/Dockerfile
                environment:
                  - POSTGRES_SERVER=db
                  - FRONTEND_HOST=http://localhost:5173
                labels:
                  - traefik.enable=true
        """,
        "compose.override.yml": "services:\n  db:\n    restart: always\n  backend:\n    command: fastapi run --reload app/main.py\n",
        "pyproject.toml": '[tool.uv.workspace]\nmembers = ["backend"]\n',
        "scripts/release.py": "print('release')\n",
        "backend/pyproject.toml": '[project]\nname = "app"\ndependencies = ["fastapi", "sqlmodel", "psycopg"]\n',
        "backend/Dockerfile": "FROM python:3.12\nCOPY ./backend /app\nCMD [\"fastapi\", \"run\", \"app/main.py\"]\n",
        "backend/app/main.py": "from fastapi import FastAPI\nfrom app.core.config import settings\napp = FastAPI()\n",
        "backend/app/core/config.py": "import os\nclass Settings:\n    FRONTEND_HOST: str = os.getenv('FRONTEND_HOST', 'http://localhost:5173')\nsettings = Settings()\n",
        "backend/app/core/db.py": "import os\nfrom sqlmodel import create_engine\nengine = create_engine(os.environ['DATABASE_URL'])\n",
        "backend/app/models.py": """
            import uuid
            from sqlmodel import Field, Relationship, SQLModel

            class UserBase(SQLModel):
                email: str = Field(unique=True, max_length=255)

            class UpdatePassword(SQLModel):
                new_password: str

            class User(UserBase, table=True):
                id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
                items: list["Item"] = Relationship(back_populates="owner")

            class Item(SQLModel, table=True):
                id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
                owner_id: uuid.UUID = Field(
                    foreign_key="user.id", nullable=False
                )
        """,
        "frontend/package.json": json.dumps({"name": "frontend", "dependencies": {"react": "19", "react-dom": "19"}, "devDependencies": {"vite": "6"}}),
        "frontend/src/main.tsx": "const base = import.meta.env.VITE_API_URL;\nexport const x = fetch(`${base}/api/v1/items`);\n",
        "packages/react-email/package.json": json.dumps({"name": "emails", "dependencies": {"react-email": "6", "@react-email/components": "1", "react": "19"}}),
        "packages/react-email/src/emails/reset.tsx": "export default function Reset() { return null }\n",
    }
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    data = build_archmap(tmp_path, log=lambda *_: None)
    nodes, links = _index(data)
    tops = {i for i, n in nodes.items() if n["parent"] is None}
    assert not any(i.startswith("svc:") for i in tops)                      # override file adds no duplicates
    assert nodes["unit:python:backend"]["compose"] == ["backend"]            # Dockerfile folder picks the unit
    assert ("res:traefik", "unit:python:backend", "calls") in links         # labels route through Traefik
    assert ("unit:python:backend", "unit:js:frontend", "calls") not in links  # FRONTEND_HOST is not a call
    assert {("actor:users", "res:traefik", "calls"), ("actor:users", "unit:js:frontend", "calls")} <= links
    assert nodes["unit:js:packages/react-email"]["kind"] == "library"
    user = {c["name"]: c for c in nodes["table:postgres:user"]["columns"]}
    assert set(user) == {"email", "id"} and user["id"].get("pk")              # inherited field, not UpdatePassword's
    item = {c["name"]: c for c in nodes["table:postgres:item"]["columns"]}
    assert item["owner_id"]["fk"] == {"table": "user", "column": "id"}
    assert ("table:postgres:item", "table:postgres:user", "references") in {(e["source"], e["target"], e["kind"]) for e in data["edges"]}


def test_share_leaves_out_local_paths(repo, tmp_path):
    from wirehouse.cli import main

    out = tmp_path / "out"
    assert main(["build", str(repo), "-o", str(out), "--share"]) == 0
    html = (out / "wirehouse.html").read_text(encoding="utf-8")
    assert str(repo) not in html and str(repo).replace("\\", "/") not in html
    assert json.dumps(str(repo))[1:-1] not in html


def test_install_reaches_every_agent_found(tmp_path, capsys):
    from wirehouse.cli import cmd_install, main

    home = tmp_path / "home"
    for marker in (".claude", ".cursor", ".gemini/antigravity"):
        (home / marker).mkdir(parents=True)
    written = {p.relative_to(home).as_posix() for p in cmd_install(home=home)}
    assert written == {".agents/skills/wirehouse/SKILL.md", ".claude/skills/wirehouse/SKILL.md",
                       ".cursor/skills/wirehouse/SKILL.md", ".gemini/skills/wirehouse/SKILL.md",
                       ".gemini/antigravity/skills/wirehouse/SKILL.md"}
    text = (home / ".agents/skills/wirehouse/SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: wirehouse") and "{{WIREHOUSE_HOME}}" not in text

    only = cmd_install(["opencode"], [str(tmp_path / "custom")], home=home)
    assert [p.relative_to(tmp_path).as_posix() for p in only] == [
        "home/.config/opencode/skills/wirehouse/SKILL.md", "custom/wirehouse/SKILL.md"]
    capsys.readouterr()
    assert main(["install", "--print"]) == 0
    assert "name: wirehouse" in capsys.readouterr().out


def _write(root: Path, files: dict) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")


def test_file_database_strings_keep_only_the_file_name(tmp_path):
    # SQLite strings are named by their file; the rest (passwords, local folders) must not reach ids or names.
    _write(tmp_path, {
        "src/App/App.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"><ItemGroup>'
                              '<PackageReference Include="Microsoft.EntityFrameworkCore.Sqlite" Version="8.0.0" />'
                              '</ItemGroup></Project>',
        "src/App/Program.cs": "var builder = WebApplication.CreateBuilder(args);\n",
        "src/App/appsettings.json": '{"ConnectionStrings": {"Default": "Data Source=app.sqlite;Password=hunter2SECRET"}}',
        "worker/requirements.txt": "sqlalchemy>=2\n",
        "worker/main.py": "import os\nfrom sqlalchemy import create_engine\nengine = create_engine(os.environ['DATABASE_URL'])\n",
        "worker/.env.example": r"DATABASE_URL=sqlite:///C:\Users\carlos\jobs.db" + "\n",
    })
    data = build_archmap(tmp_path, log=lambda *_: None)
    blob = json.dumps(data)
    assert "hunter2SECRET" not in blob and "carlos" not in blob
    assert "res:sqlite:jobs.db" in {n["id"] for n in data["nodes"]}
    from wirehouse.build import _file_instance

    assert _file_instance("Data Source=app.sqlite;Password=hunter2SECRET") == "app.sqlite"
    assert _file_instance("sqlite:///./data/app.db?mode=ro") == "app.db"


def test_added_connections_need_real_evidence(archmap):
    from wirehouse import guide

    enrichment = {"add_edges": [
        {"source": "unit:python:api", "target": "res:stripe", "kind": "calls", "description": "Charges cards.",
         "evidence": [{"file": "api/main.py", "line": 1}]},
        {"source": "unit:js:web", "target": "res:redis", "description": "no evidence"},
        {"source": "unit:js:web", "target": "res:postgres", "evidence": [{"file": "C:/Users/me/notes.py"}, "web/lib/api.ts"]},
        {"source": "unit:js:web", "target": "res:nowhere", "evidence": [{"file": "web/lib/api.ts", "line": 1}]},
    ]}
    data = guide.apply(merge(json.loads(json.dumps(archmap)), enrichment), enrichment)
    agent = [(e["source"], e["target"]) for e in data["edges"] if e.get("source_tag") == "agent"]
    assert agent == [("unit:python:api", "res:stripe")]
    codes = [d["code"] for d in data["diagnostics"]]
    assert codes.count("edge/without-evidence") == 2 and "edge/unknown-endpoint" in codes
    assert data["enrichment_stats"]["added_edges"] == 1


def test_agent_text_is_redacted_everywhere(repo, tmp_path):
    # Agent text reaches the page through more than descriptions: added nodes, edges, diagnostics.
    # None of it may carry a credential, and with --share none of it may name a local folder.
    from wirehouse.cli import main

    out = tmp_path / "out"
    out.mkdir()
    (out / "enrichment.json").write_text(json.dumps({
        "add_nodes": [{"id": "res:mailer", "name": "Mailer", "tech": ["token=abcd1234efgh"],
                       "locations": [{"file": "C:/Users/someone/private/mail.py", "line": 1}]}],
        "add_edges": [{"source": "unit:python:api", "target": "res:mailer", "description": "password=hunter22xx",
                       "evidence": [{"file": "/home/someone/x.py"}, {"file": "api/main.py", "line": 1}]},
                      {"source": "password=hunter33yy", "target": "res:mailer", "evidence": []}],
    }), encoding="utf-8")
    assert main(["build", str(repo), "-o", str(out), "--share"]) == 0
    for name in ("wirehouse.html", "archmap.json"):
        text = (out / name).read_text(encoding="utf-8")
        for leak in ("abcd1234efgh", "hunter22xx", "hunter33yy", "someone"):
            assert leak not in text, (name, leak)


def test_gitignore_rules_follow_git(tmp_path):
    from wirehouse.scan import scan

    _write(tmp_path, {
        ".gitignore": ".env*\n!.env.example\n**/generated\nappsettings.Development.json\n",
        ".env.example": "API_URL=http://api:8000\n",
        ".env.local": "API_URL=http://secret\n",
        "generated/x.py": "import os\n",
        "app/generated/y.py": "import os\n",
        "app/main.py": "import os\n",
        "app/.gitignore": "scratch.py\n",
        "app/scratch.py": "import os\n",
        "other/scratch.py": "import os\n",
        "src/Api/appsettings.json": "{}",
        "src/Api/appsettings.Development.json": '{"ConnectionStrings": {"Main": "Server=db;Password=x"}}',
    })
    res = scan(tmp_path)
    assert sorted(s.rel for s in res.sources) == ["app/main.py", "other/scratch.py"]
    assert res.configs["env_template"] == [".env.example"]                 # re-included by "!"
    assert res.configs["appsettings"] == ["src/Api/appsettings.json"]      # ignored config files are not read


def test_files_with_a_byte_order_mark_are_read(tmp_path):
    from wirehouse.enrich import load_enrichment

    bom = "﻿"
    _write(tmp_path, {"web/package.json": bom + json.dumps({"name": "web", "dependencies": {"next": "15.0.0"}}),
                      "web/app/page.tsx": "export default function Home() { return null }\n"})
    data = build_archmap(tmp_path, log=lambda *_: None)
    assert next(n for n in data["nodes"] if n["id"] == "unit:js:web")["kind"] == "frontend"
    (tmp_path / "enrichment.json").write_text(bom + '{"nodes": {}}', encoding="utf-8")
    assert load_enrichment(tmp_path) == ({"nodes": {}}, [])


@pytest.mark.parametrize("rel,body", [
    ("package.json", "[]"),
    ("package.json", '{"name": "x", "scripts": ["build"], "dependencies": ["react"]}'),
    ("docker-compose.yml", "services:\n  - web\n"),
    ("docker-compose.yml", "just a string\n"),
    ("docker-compose.yml", "services:\n  web:\n    environment: FOO\n    depends_on: db\n    profiles: dev\n"),
    (".github/workflows/ci.yml", "- step\n"),
    (".github/workflows/ci.yml", "jobs:\n  - test\n"),
    ("tsconfig.json", "[]"),
    ("tsconfig.json", '{"compilerOptions": {"baseUrl": 5, "paths": {"@/*": "./src/*"}}}'),
    ("appsettings.json", "[]"),
    ("pyproject.toml", 'project = "x"\n'),
])
def test_odd_config_shapes_do_not_stop_the_scan(tmp_path, rel, body):
    _write(tmp_path, {rel: body, "src/index.ts": "export const x = 1;\n"})
    data = build_archmap(tmp_path, log=lambda *_: None)
    assert data["nodes"]


def test_wrong_enrichment_shapes_become_diagnostics(repo, tmp_path):
    from wirehouse.cli import main

    out = tmp_path / "out"
    out.mkdir()
    (out / "enrichment.json").write_text(json.dumps({
        "nodes": {"unit:js:web": {"name": 5, "description": "The storefront."}, "unit:python:api": "text"},
        "links": {"unit:js:web->unit:python:api": "Order reads and writes."},
        "add_edges": ["web->api"],
        "remove_edges": "all",
        "add_nodes": [{"id": "table:x", "kind": "table"}],
        "tours": [{"title": "Broken", "route": [["a"], "b"]}, {"title": "Stops", "stops": [{"node": ["x"]}, "y"]}],
        "quests": [{"question": "Where?", "answer": 5}, {"question": "Infinite?", "answer": "unit:js:web",
                                                          "evidence": [{"file": "api/main.py", "line": float("inf")}]}],
    }), encoding="utf-8")
    assert main(["build", str(repo), "-o", str(out)]) == 0
    data = json.loads((out / "archmap.json").read_text(encoding="utf-8"))
    codes = [d["code"] for d in data["diagnostics"]]
    assert codes.count("enrichment/wrong-shape") >= 7
    nodes = {n["id"]: n for n in data["nodes"]}
    assert nodes["unit:js:web"]["description"] == "The storefront."
    assert data["link_notes"]["unit:js:web->unit:python:api"] == "Order reads and writes."


def test_enrichment_must_be_an_object(tmp_path):
    from wirehouse.enrich import load_enrichment

    (tmp_path / "enrichment.json").write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit, match="one JSON object"):
        load_enrichment(tmp_path)


def test_repo_info_without_git(tmp_path, monkeypatch):
    import subprocess

    from wirehouse import repo

    def missing(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", missing)
    assert repo.repo_info(tmp_path) is None


def test_long_files_scan_quickly():
    import time

    from wirehouse.detectors.code import analyze
    from wirehouse.scan import SourceFile

    text = "import x from 'y'\n" + "export const A = 1\n" * 20_000   # no `from` after the exports: the slow case
    sf = SourceFile(rel="big.ts", lang="typescript", size=len(text), text=text, sha="0", lines=20_001)
    t0 = time.perf_counter()
    facts = analyze(sf)
    assert time.perf_counter() - t0 < 5   # was ~90 s
    assert "y" in {i[0] for i in facts.imports}


def test_public_api_urls_and_cors_strings_still_connect(tmp_path):
    _write(tmp_path, {
        "docker-compose.yml": """
            services:
              web:
                build: ./web
                environment:
                  NEXT_PUBLIC_API_URL: http://api:8000
              api:
                build: ./api
        """,
        "web/package.json": json.dumps({"name": "web", "dependencies": {"next": "15.0.0"}}),
        "web/lib/api.ts": "export const base = process.env.NEXT_PUBLIC_API_URL;\n",
        "web/lib/raw.ts": "export const ping = () => fetch('http://api:8000/ping', { mode: 'cors' });\n",
        "api/requirements.txt": "fastapi\n",
        "api/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
    })
    data = build_archmap(tmp_path, log=lambda *_: None)
    calls = {(e["source"], e["target"]) for e in data["edges"]}
    assert ("file:web/lib/api.ts", "unit:python:api") in calls
    assert ("file:web/lib/raw.ts", "unit:python:api") in calls


def test_urls_in_comments_are_not_calls(tmp_path):
    _write(tmp_path, {
        "app/requirements.txt": "httpx\n",
        "app/main.py": """
            import httpx
            # see https://api.openai.com/v1/models
            # Docs: https://api.weatherstack.com/docs
            def get():
                return httpx.get("https://api.github.com/repos")
        """,
    })
    data = build_archmap(tmp_path, log=lambda *_: None)
    ids = {n["id"] for n in data["nodes"]}
    assert "ext:api.weatherstack.com" not in ids and "res:openai" not in ids
    assert any(e["target"] == "res:github" or e["target"].startswith("ext:api.github.com") for e in data["edges"])


def test_detector_details(tmp_path):
    from wirehouse.detectors.code import URL_RE, _next_route
    from wirehouse.detectors.schema import sql_columns

    _write(tmp_path, {
        "lib/requirements.txt": "pyyaml\n",
        "lib/domain.py": "class Order: ...\n",
        "svc/setup.cfg": "[options]\ninstall_requires =\n    fastapi>=0.110\n    psycopg2\n",
        "svc/app.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "pkg/setup.py": "from setuptools import setup\nsetup(install_requires=['flask'], version='1.0')\n",
        "pkg/app.py": "import flask\n",
        "db/schema.sql": "CREATE TABLE users (\n  -- the user's id\n  id INT PRIMARY KEY,\n  email TEXT\n);\n",
        "docker/Dockerfile": "FROM --platform=linux/amd64 python:3.12\nCMD [\"python\", \"main.py\"]\n",
        ".github/workflows/ci.yml": "name: CI\non: [push]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: pytest tests/test_renderer.py --project=firefly\n",
    })
    data = build_archmap(tmp_path, log=lambda *_: None)
    nodes = {n["id"]: n for n in data["nodes"]}
    assert nodes["unit:python:lib"]["kind"] == "library"
    assert nodes["unit:python:svc"]["framework"] == "FastAPI"
    assert nodes["unit:python:pkg"]["framework"] == "Flask"
    assert nodes["unit:python:db"]["framework"] == "Database schema" and "Python" not in nodes["unit:python:db"]["tech"]
    ci = next(n for n in data["nodes"] if n.get("path") == ".github/workflows/ci.yml" or n["name"] == "CI")
    assert "Deploys to" not in ci.get("description", "")
    from wirehouse.detectors.infra import detect_infra
    from wirehouse.scan import scan

    assert detect_infra(scan(tmp_path)).dockerfiles["docker/Dockerfile"].base == "python:3.12"
    sql = (tmp_path / "db/schema.sql").read_text(encoding="utf-8")
    assert [c["name"] for c in sql_columns(sql, 0)] == ["id", "email"]
    assert _next_route("web/app/pages/index.vue") == ("page", "/")
    assert URL_RE.search("https://john.doe:s3cret@api.acme.io/v1").group(1) == "api.acme.io"


def test_placeholder_text_in_the_data_stays_text(archmap):
    data = json.loads(json.dumps(archmap))
    data["project"]["name"] = "__FAVICON__ /*__CSS__*/"
    data["nodes"][0]["description"] = "html.py fills the /*__APP__*/ placeholder"
    html = render_html(data)
    assert html.count("</script>") == 3
    app_tag = html.rsplit("<script>", 1)[1]
    assert "window.__wirehouse" in app_tag      # the app landed in its own tag, not inside the data
    assert 'href="__FAVICON__"' not in html and "<title>__FAVICON__ /*__CSS__*/ · Wirehouse</title>" in html


def test_remove_edges_drops_both_directions(archmap):
    data = json.loads(json.dumps(archmap))
    enrichment = {"remove_edges": [{"source": "unit:python:api", "target": "unit:js:web"}],
                  "links": {"unit:js:web->unit:python:api": {"description": "gone"}}}
    merged = merge(data, enrichment)
    _, links = _index(merged)
    assert not {(a, b) for a, b, _ in links} & {("unit:js:web", "unit:python:api"), ("unit:python:api", "unit:js:web")}
    assert "unit:js:web->unit:python:api" not in merged["link_notes"]
    assert merged["enrichment_stats"]["removed_edges"] == 1


def test_skill_text_only_points_at_a_real_checkout(tmp_path):
    from wirehouse.cli import skill_text

    assert "pip install -e" in skill_text()                  # this source checkout
    installed = skill_text(tmp_path)                          # site-packages: no pyproject.toml
    assert "pip install -e" not in installed and "{{WIREHOUSE_HOME}}" not in installed
    assert "pip install \"git+https://github.com/creyes-git/wirehouse\"" in installed
