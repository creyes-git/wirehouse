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
