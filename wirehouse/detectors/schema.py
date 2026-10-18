"""Columns and foreign keys for tables found by detectors.code._tables.

Feeds the schema diagram inside database rooms. Like the rest of the scanner this
is regex based and favours precision: a column it cannot read is left out rather
than guessed. Only names, types and keys are kept. Default values never are,
because they can hold secrets.

Covered: SQL DDL, Prisma, SQLAlchemy, Django, Drizzle and TypeORM. EF Core and
Mongoose keep their table names only.
"""

from __future__ import annotations

import re

MAX_COLUMNS = 60
SQL_STOP = {"NOT", "NULL", "PRIMARY", "REFERENCES", "DEFAULT", "UNIQUE", "CHECK", "CONSTRAINT", "GENERATED", "COLLATE",
            "AUTO_INCREMENT", "AUTOINCREMENT", "IDENTITY", "ON", "COMMENT"}
SQL_TABLE_LEVEL = ("PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "INDEX", "KEY", "EXCLUDE", "FULLTEXT", "SPATIAL", "PERIOD")
_IDENT = re.compile(r"[\"`\[\]]")


def _unquote(name: str) -> str:
    name = _IDENT.sub("", name.strip())
    return name.split(".")[-1]


def _balanced(text: str, start: int, open_ch: str = "(", close_ch: str = ")", comment: str | None = None) -> str | None:
    """The text between a bracket and its partner. `comment` starts a line comment to skip, so an
    apostrophe in `-- the user's id` does not open a string that never closes."""
    """Text between the bracket at `start` and its match, or None."""
    if start >= len(text) or text[start] != open_ch:
        return None
    depth, quote = 0, None
    end = min(len(text), start + 200_000)
    i = start
    while i < end:
        c = text[i]
        if quote:
            if c == quote:
                quote = None
        elif comment and text.startswith(comment, i):
            nl = text.find("\n", i)
            i = end if nl < 0 else nl
            continue
        elif c in "'\"`":
            quote = c
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
        i += 1
    return None


def _split_top(body: str) -> list[str]:
    parts, depth, cur, quote = [], 0, [], None
    for c in body:
        if quote:
            cur.append(c)
            if c == quote:
                quote = None
            continue
        if c in "'\"`":
            quote = c
        elif c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    if "".join(cur).strip():
        parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _col(name: str, type_: str = "", *, pk: bool = False, fk: tuple[str, str] | None = None, null: bool | None = None) -> dict:
    c = {"name": name, "type": re.sub(r"\s+", " ", type_).strip()[:40]}
    if pk:
        c["pk"] = True
    if fk:
        c["fk"] = {"table": fk[0], "column": fk[1]}
    if null is False:
        c["required"] = True
    return c


# ── SQL DDL ──────────────────────────────────────────────────────────────────
SQL_OPEN = re.compile(r"CREATE\s+[^(;]{0,400}?\(", re.I)
SQL_REF = re.compile(r"\bREFERENCES\s+([\w.\"`\[\]]+)\s*(?:\(\s*([\w\"`\[\]]+)\s*\))?", re.I)


def sql_columns(text: str, offset: int) -> list[dict]:
    # Searched in a window: `[^(;]*?` over the rest of the file was quadratic on many `CREATE TABLE ` lines.
    m = SQL_OPEN.search(text, offset, offset + 1000)
    if not m or m.start() - offset > 400:
        return []
    body = _balanced(text, m.end() - 1, comment="--")
    if body is None:
        return []
    cols, pks, fks = [], set(), {}
    for part in _split_top(re.sub(r"--[^\n]*", "", body)):
        up = part.upper()
        if up.startswith("CONSTRAINT"):
            part = re.sub(r"^CONSTRAINT\s+\S+\s+", "", part, flags=re.I)
            up = part.upper()
        if up.startswith(SQL_TABLE_LEVEL):
            if up.startswith("PRIMARY"):
                inner = re.search(r"\(([^)]*)\)", part)
                pks.update(_unquote(x) for x in (inner.group(1).split(",") if inner else []))
            elif up.startswith("FOREIGN"):
                fm = re.search(r"FOREIGN\s+KEY\s*\(([^)]*)\)", part, re.I)
                rm = SQL_REF.search(part)
                if fm and rm:
                    fks[_unquote(fm.group(1).split(",")[0])] = (_unquote(rm.group(1)), _unquote(rm.group(2) or "id"))
            continue
        tokens = part.split()
        if len(tokens) < 2:
            continue
        type_tokens = []
        for t in tokens[1:]:
            if t.upper().split("(")[0] in SQL_STOP:
                break
            type_tokens.append(t)
        rm = SQL_REF.search(part)
        name = _unquote(tokens[0])
        cols.append(_col(name, " ".join(type_tokens), pk="PRIMARY KEY" in up, null=False if "NOT NULL" in up else None,
                         fk=(_unquote(rm.group(1)), _unquote(rm.group(2) or "id")) if rm else None))
    for c in cols:
        if c["name"] in pks:
            c["pk"] = True
        if c["name"] in fks and "fk" not in c:
            c["fk"] = {"table": fks[c["name"]][0], "column": fks[c["name"]][1]}
    return cols


# ── Prisma ───────────────────────────────────────────────────────────────────
PRISMA_FIELD = re.compile(r"^\s*(\w+)\s+(\w+)(\[\])?(\?)?(.*)$")


def prisma_columns(text: str, offset: int, models: set[str]) -> list[dict]:
    brace = text.find("{", offset)
    body = _balanced(text, brace, "{", "}", "//") if brace >= 0 else None
    if body is None:
        return []
    cols, rel_fk, pks = [], {}, set()
    for raw in body.splitlines():
        line = raw.split("//")[0].rstrip()
        if line.strip().startswith("@@id"):
            inner = re.search(r"\[([^\]]*)\]", line)
            pks.update(x.strip() for x in (inner.group(1).split(",") if inner else []))
            continue
        m = PRISMA_FIELD.match(line)
        if not m or line.strip().startswith("@@"):
            continue
        name, type_, many, optional, rest = m.groups()
        if type_ in models:   # a relation field: it names the model, the scalar column carries the key
            rm = re.search(r"fields:\s*\[([^\]]*)\][^)]*references:\s*\[([^\]]*)\]", rest)
            if rm and not many:
                rel_fk[rm.group(1).split(",")[0].strip()] = (type_, rm.group(2).split(",")[0].strip())
            continue
        cols.append(_col(name, type_ + (many or ""), pk="@id" in rest, null=None if optional else False))
    for c in cols:
        if c["name"] in pks:
            c["pk"] = True
        if c["name"] in rel_fk:
            c["fk"] = {"table": rel_fk[c["name"]][0], "column": rel_fk[c["name"]][1]}
    return cols


# ── Python ORMs ──────────────────────────────────────────────────────────────
def _py_class_body(text: str, offset: int) -> str:
    """The indented body of the class whose header is at or just before `offset`."""
    start = text.rfind("\nclass ", 0, offset + len("\nclass "))   # the header may start right at `offset`
    start = 0 if start < 0 and text.startswith("class ") else start + 1
    if start < 0 or not text.startswith("class ", start):
        return ""
    nxt = re.compile(r"^\S", re.M).search(text, text.find("\n", start) + 1)
    return text[start:nxt.start() if nxt else len(text)]


SQLA_COL = re.compile(r"^[ \t]+(\w+)\s*(?::\s*Mapped\[\s*([^\]=]+?)\s*\])?\s*=\s*(?:\w+\.)?(?:Column|mapped_column)\((.*)$", re.M)
SQLA_FK = re.compile(r"ForeignKey\(\s*['\"]([\w.]+)['\"]")


def sqlalchemy_columns(text: str, offset: int) -> list[dict]:
    cols = []
    for m in SQLA_COL.finditer(_py_class_body(text, offset)):
        name, mapped, args = m.groups()
        first = re.match(r"\s*(?:\w+\.)?([A-Z]\w*(?:\([^)]*\))?)", args)
        type_ = first.group(1) if first and first.group(1) != "ForeignKey" else (mapped or "")
        fk = SQLA_FK.search(args)
        target = fk.group(1).split(".") if fk else None
        cols.append(_col(name, type_, pk=bool(re.search(r"primary_key\s*=\s*True", args)),
                         fk=(target[-2] if len(target) > 1 else target[0], target[-1] if len(target) > 1 else "id") if target else None,
                         null=False if re.search(r"nullable\s*=\s*False", args) else None))
    return cols


DJANGO_FIELD = re.compile(r"^[ \t]+(\w+)\s*=\s*(?:models\.)?(\w+Field|ForeignKey|OneToOneField)\((.*)$", re.M)


def django_columns(text: str, offset: int) -> list[dict]:
    cols = [_col("id", "AutoField", pk=True)]
    for m in DJANGO_FIELD.finditer(_py_class_body(text, offset)):
        name, kind, args = m.groups()
        if kind in ("ForeignKey", "OneToOneField"):
            t = re.match(r"\s*['\"]?([\w.]+)['\"]?", args)
            target = t.group(1).split(".")[-1] if t else ""
            if target and target != "self":
                cols.append(_col(name + "_id", kind, fk=(target, "id"), null=None if "null=True" in args else False))
            continue
        if kind == "ManyToManyField":
            continue
        cols = [c for c in cols if not (c["name"] == "id" and "primary_key=True" in args)]
        cols.append(_col(name, kind, pk="primary_key=True" in args, null=None if "null=True" in args else False))
    return cols


SQLMODEL_FIELD = re.compile(r"^[ \t]+(\w+)\s*:\s*([^=\n#]+?)\s*(?:=\s*(.*))?$", re.M)


def sqlmodel_columns(text: str, offset: int) -> list[dict]:
    """Fields of a SQLModel table class, including those inherited from base classes in the same file."""
    classes = {m.group(1): (m.group(2), m.start()) for m in re.finditer(r"^class[ \t]+(\w+)\(([^)]*)\)\s*:", text, re.M)}
    head = re.compile(r"^class[ \t]+(\w+)\(", re.M).search(text, offset)
    if not head or head.group(1) not in classes:
        return []

    def fields(name, seen):
        if name not in classes or name in seen:
            return []
        seen.add(name)
        bases, start = classes[name]
        out = []
        for b in [x.strip() for x in bases.split(",") if "=" not in x]:
            out += fields(b, seen)
        body = _py_class_body(text, start)
        for m in SQLMODEL_FIELD.finditer(body):
            fname, type_, default = m.group(1), m.group(2).strip(), m.group(3) or ""
            if default.count("(") > default.count(")"):   # Field( ... ) spread over several lines
                full = _balanced(body, body.index("(", m.start(3)))
                default = default + (full or "")
            if fname.startswith("_") or fname == "model_config" or "Relationship(" in default or type_.startswith(("ClassVar", "list[", "List[")):
                continue
            fk = re.search(r"foreign_key\s*=\s*['\"]([\w.]+)['\"]", default)
            target = fk.group(1).split(".") if fk else None
            optional = "None" in type_ or "Optional[" in type_
            out = [c for c in out if c["name"] != fname]
            out.append(_col(fname, re.sub(r"\s*\|\s*None|Optional\[|\]$", "", type_), pk="primary_key=True" in default.replace(" ", ""),
                            fk=(target[0], target[-1]) if target and len(target) > 1 else None, null=None if optional else False))
        return out

    return fields(head.group(1), set())


# ── TypeScript ORMs ──────────────────────────────────────────────────────────
DRIZZLE_VAR = re.compile(r"\b(?:const|let|var)\s+(\w+)\s*=\s*(?:pgTable|mysqlTable|sqliteTable)\(\s*['\"](\w+)['\"]")
DRIZZLE_COL = re.compile(r"^\s*(\w+)\s*:\s*(\w+)\(\s*(?:['\"](\w+)['\"])?")


def drizzle_columns(text: str, offset: int, var_tables: dict[str, str]) -> list[dict]:
    brace = text.find("{", offset)
    body = _balanced(text, brace, "{", "}", "//") if brace >= 0 else None
    if body is None:
        return []
    cols = []
    for part in _split_top(body):
        m = DRIZZLE_COL.match(part)
        if not m:
            continue
        key, fn, colname = m.groups()
        ref = re.search(r"\.references\(\s*\(\)\s*(?::\s*\w+\s*)?=>\s*(\w+)\.(\w+)", part)
        cols.append(_col(colname or key, fn, pk=".primaryKey()" in part, null=False if ".notNull()" in part else None,
                         fk=(var_tables.get(ref.group(1), ref.group(1)), ref.group(2)) if ref else None))
    return cols


TYPEORM_DECO = re.compile(r"@(PrimaryGeneratedColumn|PrimaryColumn|Column|CreateDateColumn|UpdateDateColumn|DeleteDateColumn|ManyToOne|OneToOne)\(")
# Bounded: one property rarely has more than a few decorators, and a long run of them was quadratic.
TYPEORM_PROP = re.compile(r"\s*(?:@\w+(?:\([^)]{0,300}\))?\s*){0,12}(\w+)\s*[!?]?\s*:\s*([\w\[\]<>|. ]+)")


def typeorm_columns(text: str, offset: int) -> list[dict]:
    brace = text.find("{", offset)
    body = _balanced(text, brace, "{", "}", "//") if brace >= 0 else None
    if body is None:
        return []
    cols = []
    for m in TYPEORM_DECO.finditer(body):
        args = _balanced(body, m.end() - 1)
        if args is None:
            continue
        prop = TYPEORM_PROP.match(body, m.end() + len(args) + 1)
        if not prop:
            continue
        deco, (name, type_) = m.group(1), prop.groups()
        if deco in ("ManyToOne", "OneToOne"):
            t = re.search(r"=>\s*(\w+)", args)
            if t:
                cols.append(_col(name + "Id", "relation", fk=(t.group(1), "id")))
            continue
        cols.append(_col(name, type_.strip(), pk=deco.startswith("Primary")))
    return cols


def attach(lang: str, text: str, tables: list[dict], line_starts: list[int]) -> None:
    """Add `columns` to each table dict (in place) where the definition can be read."""
    models = set(re.findall(r"^model[ \t]+(\w+)", text, re.M)) if lang == "prisma" else set()
    var_tables = {v: t for v, t in DRIZZLE_VAR.findall(text)} if lang in ("typescript", "javascript") else {}
    for t in tables:
        offset = line_starts[t["line"] - 1] if 0 < t["line"] <= len(line_starts) else 0
        via = t.get("via", "")
        try:
            if via == "SQL DDL" and t.get("kind") == "table":
                cols = sql_columns(text, offset)
            elif via == "Prisma model":
                cols = prisma_columns(text, offset, models)
            elif via == "SQLAlchemy model":
                cols = sqlalchemy_columns(text, offset)
            elif via == "SQLModel model":
                cols = sqlmodel_columns(text, offset)
            elif via == "Django model":
                cols = django_columns(text, offset)
            elif via == "Drizzle table":
                cols = drizzle_columns(text, offset, var_tables)
            elif via == "TypeORM entity":
                cols = typeorm_columns(text, offset)
            else:
                cols = []
        except (re.error, RecursionError, IndexError):
            cols = []
        if cols:
            t["columns"] = cols[:MAX_COLUMNS]
