"""本地知识检索模块：TF-IDF + 余弦相似度，零外部依赖。

索引保存在 .ellie/index/ 下，以 JSON 文件存储。
"""

import json
import math
import re
from collections import defaultdict
from pathlib import Path


def tokenize(text):
    """简单分词：中文字符单独切，英文按空格/标点切。"""
    tokens = []
    for ch in text:
        if "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿":
            tokens.append(ch)
        elif ch.isalnum():
            tokens.append(ch.lower())
        else:
            tokens.append(" ")
    return [t for t in "".join(tokens).split() if len(t) > 1]


def build_index(docs_dir, index_dir):
    """为 docs_dir 下所有文本文件构建 TF-IDF 索引。"""
    docs_dir = Path(docs_dir)
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    documents = []
    for path in sorted(docs_dir.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if len(text.strip()) < 20:
            continue
        documents.append({
            "id": str(path.relative_to(docs_dir)),
            "path": str(path),
            "text": text,
        })

    # 构建倒排索引（简化 TF-IDF）
    df = defaultdict(int)  # document frequency
    doc_tokens = []
    for doc in documents:
        tokens = tokenize(doc["text"])
        unique_tokens = set(tokens)
        doc_tokens.append(tokens)
        for t in unique_tokens:
            df[t] += 1

    N = len(documents)
    # 存储 TF-IDF 向量（稀疏）
    vectors = []
    for tokens in doc_tokens:
        tf = defaultdict(float)
        for t in tokens:
            tf[t] += 1.0 / len(tokens)
        vec = {t: tf[t] * (math.log(N / (df[t] + 1)) + 1) for t in set(tokens)}
        vectors.append(vec)

    index_data = {
        "documents": [{"id": d["id"], "path": d["path"]} for d in documents],
        "vectors": vectors,
        "total_docs": N,
    }
    (index_dir / "index.json").write_text(
        json.dumps(index_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return N


def search(query, index_dir, top_k=5):
    """在已建索引中检索与 query 最相关的 top_k 个文档片段。"""
    index_dir = Path(index_dir)
    index_path = index_dir / "index.json"
    if not index_path.exists():
        return []

    data = json.loads(index_path.read_text(encoding="utf-8"))
    documents = data["documents"]
    vectors = data["vectors"]

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    # 构建 query 向量
    query_vec = defaultdict(float)
    N = len(documents)
    for t in query_tokens:
        df_t = sum(1 for v in vectors if t in v)
        tf = query_tokens.count(t) / len(query_tokens)
        query_vec[t] = tf * (math.log(N / (df_t + 1)) + 1)

    # 余弦相似度
    scores = []
    for i, doc_vec in enumerate(vectors):
        dot = sum(query_vec[t] * doc_vec.get(t, 0) for t in query_vec)
        q_norm = math.sqrt(sum(v ** 2 for v in query_vec.values()))
        d_norm = math.sqrt(sum(v ** 2 for v in doc_vec.values()))
        if q_norm == 0 or d_norm == 0:
            continue
        scores.append((dot / (q_norm * d_norm), i))

    scores.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, idx in scores[:top_k]:
        if score < 0.1:
            continue
        doc = documents[idx]
        path = Path(doc["path"])
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # 找到最相关的段落（简单滑动窗口）
        paragraphs = text.split("\n\n")
        best_para = ""
        best_score = 0
        for para in paragraphs:
            para_tokens = set(tokenize(para))
            overlap = len(para_tokens & set(query_tokens))
            if overlap > best_score:
                best_score = overlap
                best_para = para.strip()[:500]

        results.append({
            "source": doc["id"],
            "score": round(score, 3),
            "snippet": best_para or text.strip()[:500],
        })

    return results
