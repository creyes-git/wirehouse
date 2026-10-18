"""Known technologies: how to recognise them and which warehouse block they become.

Each signature can match on:
- npm / pypi / nuget: dependency names in manifests (npm entries ending in "/" are scope prefixes)
- py: Python import roots; js: JS import specifiers (defaults to npm); ns: C# namespace prefixes
- code: regexes that indicate use inside a source file (e.g. a connection call)
- hosts: hostnames found in URLs inside code or config
- images: docker image name prefixes (compose)
- schemes: URL schemes / file extensions in env values (postgres://, .duckdb, ...)

`role` marks things that are tooling for another signature rather than a block
of their own (ORMs, drivers-only frameworks): they add tech tags, not nodes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Signature:
    id: str
    name: str
    kind: str
    npm: list[str] = field(default_factory=list)
    pypi: list[str] = field(default_factory=list)
    py: list[str] = field(default_factory=list)
    nuget: list[str] = field(default_factory=list)
    ns: list[str] = field(default_factory=list)
    code: list[str] = field(default_factory=list)
    hosts: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    schemes: list[str] = field(default_factory=list)
    tech: str = ""
    role: str = "block"  # block | orm
    _code_re: list = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._code_re = [re.compile(p) for p in self.code]
        if not self.tech:
            self.tech = self.name


def S(id, name, kind, **kw) -> Signature:
    return Signature(id=id, name=name, kind=kind, **kw)


SIGNATURES: list[Signature] = [
    # ── Databases ────────────────────────────────────────────────────────────
    S("postgres", "PostgreSQL", "database",
      npm=["pg", "postgres", "@neondatabase/serverless", "@vercel/postgres", "pg-promise", "slonik"],
      pypi=["psycopg", "psycopg2", "psycopg2-binary", "asyncpg", "pg8000"], py=["psycopg", "psycopg2", "asyncpg", "pg8000"],
      nuget=["Npgsql", "Npgsql.EntityFrameworkCore.PostgreSQL"], ns=["Npgsql"],
      code=[r"UseNpgsql\(", r"postgres(?:ql)?(?:\+\w+)?://"], images=["postgres", "postgis/", "bitnami/postgresql", "timescale/"],
      schemes=["postgres://", "postgresql://", "postgresql+"]),
    S("mysql", "MySQL", "database",
      npm=["mysql", "mysql2", "@planetscale/database"], pypi=["pymysql", "mysqlclient", "aiomysql", "mysql-connector-python"],
      py=["pymysql", "MySQLdb", "aiomysql", "mysql"], nuget=["MySql.Data", "MySqlConnector", "Pomelo.EntityFrameworkCore.MySql"],
      ns=["MySql", "MySqlConnector"], code=[r"UseMySql\("], images=["mysql", "mariadb", "bitnami/mysql"],
      schemes=["mysql://", "mysql+", "mariadb://"]),
    S("sqlserver", "SQL Server", "database",
      npm=["mssql", "tedious"], pypi=["pymssql", "pyodbc"], py=["pymssql", "pyodbc"],
      nuget=["Microsoft.Data.SqlClient", "System.Data.SqlClient", "Microsoft.EntityFrameworkCore.SqlServer", "Dapper"],
      ns=["Microsoft.Data.SqlClient", "System.Data.SqlClient"], code=[r"UseSqlServer\(", r"new SqlConnection\("],
      images=["mcr.microsoft.com/mssql", "mcr.microsoft.com/azure-sql-edge"], schemes=["mssql://", "mssql+", "sqlserver://"]),
    S("sqlite", "SQLite", "database",
      npm=["better-sqlite3", "sqlite3", "sqlite", "@libsql/client"], py=["sqlite3", "aiosqlite"], pypi=["aiosqlite"],
      nuget=["Microsoft.Data.Sqlite", "Microsoft.EntityFrameworkCore.Sqlite", "System.Data.SQLite"],
      ns=["Microsoft.Data.Sqlite"], code=[r"UseSqlite\(", r"sqlite(?:\+\w+)?:///"],
      schemes=["sqlite://", "sqlite+", "libsql://", ".db", ".sqlite", ".sqlite3"]),
    S("duckdb", "DuckDB", "database", npm=["duckdb", "@duckdb/"], pypi=["duckdb"], py=["duckdb"],
      nuget=["DuckDB.NET.Data"], ns=["DuckDB"], schemes=[".duckdb", "duckdb://"]),
    S("mongodb", "MongoDB", "database", npm=["mongodb", "mongoose"], pypi=["pymongo", "motor", "mongoengine", "beanie"],
      py=["pymongo", "motor", "mongoengine", "beanie"], nuget=["MongoDB.Driver"], ns=["MongoDB"],
      images=["mongo", "bitnami/mongodb"], schemes=["mongodb://", "mongodb+srv://"]),
    S("cosmos", "Azure Cosmos DB", "database", npm=["@azure/cosmos"], pypi=["azure-cosmos"], py=["azure.cosmos"],
      nuget=["Microsoft.Azure.Cosmos"], ns=["Microsoft.Azure.Cosmos"], hosts=[".documents.azure.com"]),
    S("dynamodb", "DynamoDB", "database", npm=["@aws-sdk/client-dynamodb", "@aws-sdk/lib-dynamodb", "dynamoose"],
      code=[r"boto3\.(?:client|resource)\(\s*['\"]dynamodb"], nuget=["AWSSDK.DynamoDBv2"], ns=["Amazon.DynamoDBv2"]),
    S("firestore", "Firebase / Firestore", "database", npm=["firebase", "firebase-admin"], pypi=["firebase-admin", "google-cloud-firestore"],
      py=["firebase_admin", "google.cloud.firestore"], nuget=["Google.Cloud.Firestore", "FirebaseAdmin"], ns=["Google.Cloud.Firestore"]),
    S("supabase", "Supabase", "database", npm=["@supabase/supabase-js", "@supabase/ssr", "@supabase/auth-helpers-nextjs"],
      pypi=["supabase"], py=["supabase"], hosts=[".supabase.co"]),
    S("clickhouse", "ClickHouse", "database", npm=["@clickhouse/client"], pypi=["clickhouse-connect", "clickhouse-driver"],
      py=["clickhouse_connect", "clickhouse_driver"], images=["clickhouse/", "yandex/clickhouse"], schemes=["clickhouse://"]),
    S("snowflake", "Snowflake", "database", npm=["snowflake-sdk"], pypi=["snowflake-connector-python"], py=["snowflake"],
      hosts=[".snowflakecomputing.com"]),
    S("bigquery", "BigQuery", "database", npm=["@google-cloud/bigquery"], pypi=["google-cloud-bigquery"], py=["google.cloud.bigquery"]),
    S("neo4j", "Neo4j", "database", npm=["neo4j-driver"], pypi=["neo4j"], py=["neo4j"], images=["neo4j"], schemes=["neo4j://", "bolt://"]),
    S("pinecone", "Pinecone", "search", npm=["@pinecone-database/pinecone"], pypi=["pinecone", "pinecone-client"], py=["pinecone"]),
    S("qdrant", "Qdrant", "search", npm=["@qdrant/js-client-rest"], pypi=["qdrant-client"], py=["qdrant_client"], images=["qdrant/"]),
    S("chroma", "Chroma", "search", npm=["chromadb"], pypi=["chromadb"], py=["chromadb"], images=["chromadb/"]),
    S("elasticsearch", "Elasticsearch", "search", npm=["@elastic/elasticsearch"], pypi=["elasticsearch"], py=["elasticsearch"],
      nuget=["Elastic.Clients.Elasticsearch", "NEST"], images=["elasticsearch", "docker.elastic.co/elasticsearch", "opensearchproject/"]),
    S("meilisearch", "Meilisearch", "search", npm=["meilisearch"], pypi=["meilisearch"], py=["meilisearch"], images=["getmeili/"]),
    S("algolia", "Algolia", "search", npm=["algoliasearch"], pypi=["algoliasearch"], py=["algoliasearch"], hosts=[".algolia.net"]),
    # ── Caches & queues ─────────────────────────────────────────────────────
    S("redis", "Redis", "cache", npm=["redis", "ioredis", "@upstash/redis", "@redis/client"], pypi=["redis", "aioredis"],
      py=["redis", "aioredis"], nuget=["StackExchange.Redis", "Microsoft.Extensions.Caching.StackExchangeRedis"],
      ns=["StackExchange.Redis"], images=["redis", "bitnami/redis", "valkey/"], schemes=["redis://", "rediss://"]),
    S("memcached", "Memcached", "cache", npm=["memcached"], pypi=["pymemcache", "python-memcached"], py=["pymemcache", "memcache"],
      images=["memcached"]),
    S("rabbitmq", "RabbitMQ", "queue", npm=["amqplib", "amqp-connection-manager"], pypi=["pika", "aio-pika", "kombu"],
      py=["pika", "aio_pika"], nuget=["RabbitMQ.Client", "MassTransit.RabbitMQ"], ns=["RabbitMQ"], images=["rabbitmq"],
      schemes=["amqp://", "amqps://"]),
    S("kafka", "Kafka", "queue", npm=["kafkajs", "node-rdkafka"], pypi=["kafka-python", "confluent-kafka", "aiokafka"],
      py=["kafka", "confluent_kafka", "aiokafka"], nuget=["Confluent.Kafka"], ns=["Confluent.Kafka"],
      images=["confluentinc/", "bitnami/kafka", "apache/kafka", "redpandadata/"]),
    S("sqs", "AWS SQS", "queue", npm=["@aws-sdk/client-sqs"], code=[r"boto3\.(?:client|resource)\(\s*['\"]sqs"],
      nuget=["AWSSDK.SQS"], ns=["Amazon.SQS"]),
    S("sns", "AWS SNS", "queue", npm=["@aws-sdk/client-sns"], code=[r"boto3\.client\(\s*['\"]sns"], nuget=["AWSSDK.SimpleNotificationService"]),
    S("servicebus", "Azure Service Bus", "queue", npm=["@azure/service-bus"], pypi=["azure-servicebus"], py=["azure.servicebus"],
      nuget=["Azure.Messaging.ServiceBus", "MassTransit.Azure.ServiceBus.Core"], ns=["Azure.Messaging.ServiceBus"]),
    S("pubsub", "Google Pub/Sub", "queue", npm=["@google-cloud/pubsub"], pypi=["google-cloud-pubsub"], py=["google.cloud.pubsub"]),
    S("nats", "NATS", "queue", npm=["nats"], pypi=["nats-py"], py=["nats"], nuget=["NATS.Client"], images=["nats"], schemes=["nats://"]),
    S("bullmq", "BullMQ", "queue", npm=["bullmq", "bull", "bee-queue"]),
    S("celery", "Celery", "queue", pypi=["celery"], py=["celery"]),
    S("hangfire", "Hangfire", "queue", nuget=["Hangfire", "Hangfire.Core", "Hangfire.AspNetCore"], ns=["Hangfire"]),
    S("inngest", "Inngest", "queue", npm=["inngest"], pypi=["inngest"], py=["inngest"]),
    # ── Object / file storage ───────────────────────────────────────────────
    S("s3", "AWS S3", "storage", npm=["@aws-sdk/client-s3", "@aws-sdk/s3-request-presigner"],
      code=[r"boto3\.(?:client|resource)\(\s*['\"]s3"], nuget=["AWSSDK.S3"], ns=["Amazon.S3"], hosts=[".s3.amazonaws.com", "s3.amazonaws.com"]),
    S("azureblob", "Azure Blob Storage", "storage", npm=["@azure/storage-blob"], pypi=["azure-storage-blob"], py=["azure.storage.blob"],
      nuget=["Azure.Storage.Blobs"], ns=["Azure.Storage.Blobs"], hosts=[".blob.core.windows.net"]),
    S("gcs", "Google Cloud Storage", "storage", npm=["@google-cloud/storage"], pypi=["google-cloud-storage"], py=["google.cloud.storage"]),
    S("minio", "MinIO", "storage", npm=["minio"], pypi=["minio"], py=["minio"], images=["minio/", "bitnami/minio"]),
    S("cloudinary", "Cloudinary", "storage", npm=["cloudinary", "next-cloudinary"], pypi=["cloudinary"], py=["cloudinary"],
      hosts=["res.cloudinary.com", "api.cloudinary.com"]),
    S("uploadthing", "UploadThing", "storage", npm=["uploadthing", "@uploadthing/"]),
    S("vercelblob", "Vercel Blob", "storage", npm=["@vercel/blob"]),
    S("r2", "Cloudflare R2", "storage", hosts=[".r2.cloudflarestorage.com"]),
    # ── Auth ────────────────────────────────────────────────────────────────
    S("nextauth", "Auth.js / NextAuth", "auth", npm=["next-auth", "@auth/"]),
    S("clerk", "Clerk", "auth", npm=["@clerk/"], pypi=["clerk-backend-api"], hosts=[".clerk.accounts.dev", "api.clerk.com"]),
    S("auth0", "Auth0", "auth", npm=["@auth0/", "auth0"], pypi=["auth0-python"], py=["auth0"],
      nuget=["Auth0.AspNetCore.Authentication", "Auth0.AuthenticationApi"], hosts=[".auth0.com"]),
    S("supabase_auth", "Supabase Auth", "auth", code=[r"supabase\.auth\.", r"auth\.getUser\(", r"auth\.signIn"]),
    S("firebase_auth", "Firebase Auth", "auth", code=[r"from ['\"]firebase/auth['\"]", r"firebase_admin\s+import\s+auth", r"getAuth\("]),
    S("cognito", "AWS Cognito", "auth", npm=["amazon-cognito-identity-js", "@aws-sdk/client-cognito-identity-provider"],
      code=[r"boto3\.client\(\s*['\"]cognito"], nuget=["Amazon.Extensions.CognitoAuthentication"]),
    S("entra", "Microsoft Entra ID", "auth", npm=["@azure/msal-browser", "@azure/msal-node", "@azure/msal-react"],
      pypi=["msal"], py=["msal"], nuget=["Microsoft.Identity.Web", "Microsoft.Identity.Client"], ns=["Microsoft.Identity"],
      hosts=["login.microsoftonline.com"]),
    S("okta", "Okta", "auth", npm=["@okta/"], pypi=["okta"], nuget=["Okta.AspNetCore"], hosts=[".okta.com"]),
    S("keycloak", "Keycloak", "auth", npm=["keycloak-js", "keycloak-connect"], pypi=["python-keycloak"], py=["keycloak"],
      images=["quay.io/keycloak/", "jboss/keycloak", "bitnami/keycloak"]),
    S("kinde", "Kinde", "auth", npm=["@kinde-oss/"]),
    S("betterauth", "Better Auth", "auth", npm=["better-auth"]),
    S("lucia", "Lucia", "auth", npm=["lucia", "@lucia-auth/"]),
    S("passport", "Passport.js", "auth", npm=["passport", "passport-"]),
    S("jwt", "JWT tokens", "auth", npm=["jsonwebtoken", "jose", "jwt-decode", "@fastify/jwt"],
      pypi=["pyjwt", "python-jose", "authlib"], py=["jwt", "jose", "authlib"],
      nuget=["Microsoft.AspNetCore.Authentication.JwtBearer", "System.IdentityModel.Tokens.Jwt"], ns=["Microsoft.AspNetCore.Authentication.JwtBearer"],
      code=[r"AddJwtBearer\("]),
    S("aspnet_identity", "ASP.NET Identity", "auth", nuget=["Microsoft.AspNetCore.Identity.EntityFrameworkCore", "Microsoft.AspNetCore.Identity.UI"],
      code=[r"AddIdentity(?:Core)?<", r"AddDefaultIdentity<"]),
    S("django_auth", "Django auth", "auth", code=[r"from django\.contrib\.auth", r"django\.contrib\.auth"]),
    S("flask_login", "Flask-Login", "auth", pypi=["flask-login"], py=["flask_login"]),
    S("fastapi_security", "FastAPI security", "auth", code=[r"from fastapi\.security import", r"OAuth2PasswordBearer\(", r"HTTPBearer\("]),
    # ── AI providers ─────────────────────────────────────────────────────────
    S("anthropic", "Anthropic Claude API", "ai", npm=["@anthropic-ai/sdk", "@ai-sdk/anthropic"], pypi=["anthropic"], py=["anthropic"],
      nuget=["Anthropic.SDK", "Anthropic"], hosts=["api.anthropic.com"]),
    S("openai", "OpenAI API", "ai", npm=["openai", "@ai-sdk/openai"], pypi=["openai"], py=["openai"],
      nuget=["OpenAI", "Azure.AI.OpenAI"], ns=["OpenAI", "Azure.AI.OpenAI"], hosts=["api.openai.com", ".openai.azure.com"]),
    S("openrouter", "OpenRouter", "ai", npm=["@openrouter/ai-sdk-provider"], hosts=["openrouter.ai"]),
    S("gemini", "Google Gemini", "ai", npm=["@google/generative-ai", "@google/genai", "@ai-sdk/google"],
      pypi=["google-generativeai", "google-genai"], py=["google.generativeai", "google.genai"], hosts=["generativelanguage.googleapis.com"]),
    S("mistral", "Mistral AI", "ai", npm=["@mistralai/mistralai"], pypi=["mistralai"], py=["mistralai"], hosts=["api.mistral.ai"]),
    S("cohere", "Cohere", "ai", npm=["cohere-ai"], pypi=["cohere"], py=["cohere"]),
    S("groq", "Groq", "ai", npm=["groq-sdk"], pypi=["groq"], py=["groq"], hosts=["api.groq.com"]),
    S("huggingface", "Hugging Face", "ai", npm=["@huggingface/inference"], pypi=["huggingface-hub"], py=["huggingface_hub"],
      hosts=["huggingface.co", "api-inference.huggingface.co"]),
    S("replicate", "Replicate", "ai", npm=["replicate"], pypi=["replicate"], py=["replicate"], hosts=["api.replicate.com"]),
    S("ollama", "Ollama", "ai", npm=["ollama"], pypi=["ollama"], py=["ollama"], images=["ollama/"]),
    S("bedrock", "AWS Bedrock", "ai", npm=["@aws-sdk/client-bedrock-runtime"], code=[r"boto3\.client\(\s*['\"]bedrock"]),
    # ── Payments, messaging, other SaaS ──────────────────────────────────────
    S("stripe", "Stripe", "external", npm=["stripe", "@stripe/"], pypi=["stripe"], py=["stripe"], nuget=["Stripe.net"], ns=["Stripe"],
      hosts=["api.stripe.com"]),
    S("paypal", "PayPal", "external", npm=["@paypal/"], pypi=["paypalrestsdk"], hosts=["api.paypal.com", "api-m.paypal.com"]),
    S("lemonsqueezy", "Lemon Squeezy", "external", npm=["@lemonsqueezy/"]),
    S("twilio", "Twilio", "external", npm=["twilio"], pypi=["twilio"], py=["twilio"], nuget=["Twilio"], hosts=["api.twilio.com"]),
    S("sendgrid", "SendGrid", "external", npm=["@sendgrid/"], pypi=["sendgrid"], py=["sendgrid"], nuget=["SendGrid"], hosts=["api.sendgrid.com"]),
    S("resend", "Resend", "external", npm=["resend"], pypi=["resend"], py=["resend"], hosts=["api.resend.com"]),
    S("postmark", "Postmark", "external", npm=["postmark"], pypi=["postmarker"], hosts=["api.postmarkapp.com"]),
    S("mailgun", "Mailgun", "external", npm=["mailgun.js", "mailgun-js"], hosts=["api.mailgun.net"]),
    S("smtp", "SMTP email", "external", npm=["nodemailer"], py=["smtplib", "aiosmtplib"], nuget=["MailKit"], ns=["MailKit", "System.Net.Mail"]),
    S("slack", "Slack", "external", npm=["@slack/"], pypi=["slack-sdk", "slack-bolt"], py=["slack_sdk", "slack_bolt"], hosts=["slack.com", "hooks.slack.com"]),
    S("discord", "Discord", "external", npm=["discord.js"], pypi=["discord.py"], py=["discord"], hosts=["discord.com"]),
    S("github", "GitHub API", "external", npm=["@octokit/", "octokit"], pypi=["pygithub"], py=["github"], nuget=["Octokit"], hosts=["api.github.com"]),
    S("msgraph", "Microsoft Graph", "external", npm=["@microsoft/microsoft-graph-client"], pypi=["msgraph-sdk"], nuget=["Microsoft.Graph"],
      ns=["Microsoft.Graph"], hosts=["graph.microsoft.com"]),
    S("googleapis", "Google APIs", "external", npm=["googleapis", "@googleapis/"], pypi=["google-api-python-client"], py=["googleapiclient"],
      hosts=["www.googleapis.com", "sheets.googleapis.com"]),
    S("mapbox", "Mapbox", "external", npm=["mapbox-gl", "@mapbox/"], hosts=["api.mapbox.com"]),
    S("googlemaps", "Google Maps", "external", npm=["@googlemaps/", "@react-google-maps/api"], pypi=["googlemaps"], hosts=["maps.googleapis.com"]),
    S("shopify", "Shopify", "external", npm=["@shopify/"], pypi=["shopifyapi"], hosts=[".myshopify.com"]),
    S("hubspot", "HubSpot", "external", npm=["@hubspot/api-client"], pypi=["hubspot-api-client"], hosts=["api.hubapi.com"]),
    S("salesforce", "Salesforce", "external", npm=["jsforce"], pypi=["simple-salesforce"], hosts=[".salesforce.com"]),
    S("posthog", "PostHog", "external", npm=["posthog-js", "posthog-node"], pypi=["posthog"], py=["posthog"], hosts=["app.posthog.com", "us.i.posthog.com"]),
    S("segment", "Segment", "external", npm=["@segment/"], hosts=["api.segment.io"]),
    S("mixpanel", "Mixpanel", "external", npm=["mixpanel", "mixpanel-browser"], pypi=["mixpanel"]),
    S("yahoo_finance", "Yahoo Finance", "external", npm=["yahoo-finance2", "yahoo-finance"], pypi=["yfinance", "yahooquery"],
      py=["yfinance", "yahooquery"], hosts=["query1.finance.yahoo.com", "query2.finance.yahoo.com", "finance.yahoo.com"]),
    S("sec_edgar", "SEC EDGAR", "external", pypi=["edgartools", "sec-edgar-downloader", "sec-api"], py=["edgar", "sec_edgar_downloader", "sec_api"],
      hosts=["www.sec.gov", "data.sec.gov", "efts.sec.gov"]),
    S("logodev", "logo.dev", "external", hosts=["img.logo.dev", "logo.dev"]),
    S("wikidata", "Wikidata", "external", hosts=["www.wikidata.org", "query.wikidata.org", "wikidata.org"]),
    # ── Observability (Ops zone) ─────────────────────────────────────────────
    S("sentry", "Sentry", "observability", npm=["@sentry/"], pypi=["sentry-sdk"], py=["sentry_sdk"], nuget=["Sentry", "Sentry.AspNetCore"],
      hosts=[".sentry.io", ".ingest.sentry.io"]),
    S("datadog", "Datadog", "observability", npm=["dd-trace", "@datadog/"], pypi=["ddtrace", "datadog"], py=["ddtrace", "datadog"]),
    S("newrelic", "New Relic", "observability", npm=["newrelic"], pypi=["newrelic"], py=["newrelic"]),
    S("otel", "OpenTelemetry", "observability", npm=["@opentelemetry/"], pypi=["opentelemetry-api", "opentelemetry-sdk"], py=["opentelemetry"],
      nuget=["OpenTelemetry"], ns=["OpenTelemetry"], images=["otel/"]),
    S("prometheus", "Prometheus", "observability", npm=["prom-client"], pypi=["prometheus-client"], py=["prometheus_client"],
      nuget=["prometheus-net"], images=["prom/prometheus"]),
    S("grafana", "Grafana", "observability", images=["grafana/"]),
    S("appinsights", "Application Insights", "observability", npm=["applicationinsights", "@microsoft/applicationinsights-web"],
      pypi=["opencensus-ext-azure", "azure-monitor-opentelemetry"], nuget=["Microsoft.ApplicationInsights.AspNetCore"]),
    # ── Gateways (Edge zone) ─────────────────────────────────────────────────
    S("nginx", "Nginx", "gateway", images=["nginx", "bitnami/nginx"]),
    S("traefik", "Traefik", "gateway", images=["traefik"]),
    S("caddy", "Caddy", "gateway", images=["caddy"]),
    S("kong", "Kong", "gateway", images=["kong"]),
    S("yarp", "YARP reverse proxy", "gateway", nuget=["Yarp.ReverseProxy"]),
    S("ocelot", "Ocelot gateway", "gateway", nuget=["Ocelot"]),
    # ── ORMs (tech tags on the edge to the database, not blocks) ────────────
    S("prisma", "Prisma", "orm", npm=["@prisma/client", "prisma"], role="orm"),
    S("drizzle", "Drizzle", "orm", npm=["drizzle-orm"], role="orm"),
    S("typeorm", "TypeORM", "orm", npm=["typeorm"], role="orm"),
    S("sequelize", "Sequelize", "orm", npm=["sequelize"], role="orm"),
    S("kysely", "Kysely", "orm", npm=["kysely"], role="orm"),
    S("sqlalchemy", "SQLAlchemy", "orm", pypi=["sqlalchemy", "sqlmodel"], py=["sqlalchemy", "sqlmodel"], role="orm"),
    S("django_orm", "Django ORM", "orm", py=["django.db"], role="orm"),
    S("efcore", "Entity Framework Core", "orm", nuget=["Microsoft.EntityFrameworkCore"], ns=["Microsoft.EntityFrameworkCore"], role="orm"),
]

BY_ID = {s.id: s for s in SIGNATURES}


def _norm_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def match_npm(pkg: str) -> list[Signature]:
    out = []
    for s in SIGNATURES:
        for p in s.npm:
            if (p.endswith("/") and pkg.startswith(p)) or (p.endswith("-") and pkg.startswith(p)) or pkg == p:
                out.append(s)
                break
    return out


def match_pypi(pkg: str) -> list[Signature]:
    n = _norm_pkg(pkg)
    return [s for s in SIGNATURES if any(_norm_pkg(p) == n for p in s.pypi)]


def match_nuget(pkg: str) -> list[Signature]:
    low = pkg.lower()
    return [s for s in SIGNATURES if any(p.lower() == low for p in s.nuget)]


def match_py_import(module: str) -> list[Signature]:
    out = []
    for s in SIGNATURES:
        for m in s.py:
            if module == m or module.startswith(m + "."):
                out.append(s)
                break
    return out


def match_cs_namespace(ns: str) -> list[Signature]:
    out = []
    for s in SIGNATURES:
        for p in s.ns:
            if ns == p or ns.startswith(p + "."):
                out.append(s)
                break
    return out


def match_host(host: str) -> list[Signature]:
    host = host.lower()
    out = []
    for s in SIGNATURES:
        for h in s.hosts:
            if (h.startswith(".") and host.endswith(h)) or host == h or host.endswith("." + h):
                out.append(s)
                break
    return out


def match_image(image: str) -> list[Signature]:
    img = image.lower().split("@")[0]
    base = img.split(":")[0]
    out = []
    for s in SIGNATURES:
        for p in s.images:
            if (p.endswith("/") and base.startswith(p)) or base == p or base.endswith("/" + p) or base == "library/" + p:
                out.append(s)
                break
    return out


def match_value(value: str) -> list[Signature]:
    """Match an env/config value such as a connection URL or a database file path."""
    v = value.strip().strip("'\"").lower()
    out = []
    for s in SIGNATURES:
        for sch in s.schemes:
            if sch.startswith("."):
                path = v.split("?")[0]
                if path.endswith(sch) and "://" not in path.replace("sqlite:///", ""):
                    out.append(s)
                    break
            elif v.startswith(sch):
                out.append(s)
                break
    # ADO.NET style connection strings
    if not out and "=" in v and ";" in v:
        if "host=" in v and ("username=" in v or "database=" in v):
            out.append(BY_ID["postgres"])
        elif ("server=" in v or "data source=" in v) and ("database=" in v or "initial catalog=" in v):
            out.append(BY_ID["sqlserver"])
        elif "data source=" in v and (v.rstrip(";").endswith(".db") or ".sqlite" in v):
            out.append(BY_ID["sqlite"])
    return out
