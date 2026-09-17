# -*- coding: utf-8 -*-
"""Диагностика: что видит GUI и что находит поиск на реальных вопросах."""
import json, urllib.parse, urllib.request, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aila_core.rag import RagEngine, tokenize, query_hints
from aila_core import config

print("=== статус сервера ===")
d = json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/status", timeout=10))
print("llm :", d["llm"])
print("rag :", d["rag"])

print()
print("=== карта документа (парсер kmhto) ===")
print("  digest:", d["rag"].get("sheets", []))
for sheet in d["rag"].get("sheets_info", []):
    print(f"  лист {sheet['name']!r}: роль {sheet['role']}, строк {sheet['rows']}, "
          f"кодов {sheet['codes']}, месяцев {sheet['months']}")
print("  опечаток в данных:", d["rag"].get("typos"), d["rag"].get("typo_examples", [])[:3])
from aila_core import kmhto
print("  роли листов по парсеру:", {n: kmhto.sheet_role(n) for n in ("1", "3", "data", "коды")})
print("  'грязные' ячейки:", kmhto.parse_days("14,\n20,\n2"), kmhto.parse_days("0, 32, 5"),
      "| работы:", kmhto.parse_work_items("ТО-3( 10 )"))
print("  самотест парсера: .venv_311\\Scripts\\python.exe -m aila_core.kmhto")

print()
print("=== токенизация (что реально ищется) ===")
for q in ["когда проводят ТО-3", "какое оборудование под кодом 3", "расскажи про график ТО"]:
    print(" ", q, "->", tokenize(q), "| hints:", query_hints(q))

print()
print("=== поиск из живого индекса ===")
eng = RagEngine()
eng.ensure_loaded(config.sample_document())
questions = [
    "когда проводят ТО-3",
    "какое оборудование под кодом 3",
    "график ТО влагомера",
    "что такое СИКН",
    "расскажи про преобразователь расхода",
    "какая поверка у датчика давления",
    "привет",
    "сколько оборудования всего",
]
for q in questions:
    hits = eng.search(q, 3)
    print(f"\n  Q: {q}  -> найдено {len(hits)}")
    for h in hits:
        print(f"     {h['score']:.3f} {h['id']:12} {h['meta'].get('equipment','')[:60]}")
