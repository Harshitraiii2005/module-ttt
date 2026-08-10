import math

from typing import Dict, List
from collections import Counter

from app.services.package_text_tokenizer import TextTokenizer
from app.services.package_symbol_generator import SymbolGenerator
from talkingdb.helpers.graph_cache import graph_cache
from app.core.thread_pool import executor
from app.core import config

ELEMENT_TYPES = config.RETRIEVAL_ELEMENT_TYPES
GRAM_WEIGHTS = config.GRAM_WEIGHTS
CONTEXT_WEIGHT = config.CONTEXT_MATCH_WEIGHT
MAX_ROWS_PER_TABLE = config.MAX_ROWS_PER_TABLE


class ExtractorService:

    def __init__(self, graph_ids: List[str], max_matches: int = 10):
        self.gms = [graph_cache.get(gid) for gid in graph_ids]

        self.max_matches = max_matches
        self.tokenizer = TextTokenizer()
        self.symbol_generator = SymbolGenerator()

        self._element_counts: Dict[str, int] = {}
        self.executor = executor

    # ─────────────────────────────────────────────────────────────

    def extract(self, query: str):
        """Score all gram orders using gram-order and IDF weighting.
        Avoid early unigram matches so higher-order grams can contribute.
        """
        elements = Counter()
        symbols = Counter()

        prose = self.symbol_generator.generate(self.tokenizer.tokenize(query))
        structured = self.symbol_generator.generate(
            self.tokenizer.tokenize_structured(query)
        )

        for gram in self.symbol_generator.grams():
            prose_symbols = prose.get(gram, [])
            seen = set(prose_symbols)
            extra = [s for s in structured.get(gram, []) if s not in seen]
            query_symbols = prose_symbols + extra

            if not query_symbols:
                continue

            matched_elements, matched_symbols = self._collect_paragraphs(
                query_symbols, gram
            )

            weight = GRAM_WEIGHTS.get(gram, 1)

            for element_id, score in matched_elements.items():
                elements[element_id] += score * weight

            for symbol_id, score in matched_symbols.items():
                symbols[symbol_id] += score * weight

        return self.get_scores(symbols, elements)

    # ─────────────────────────────────────────────────────────────

    def _element_count(self, gm) -> int:
        cached = self._element_counts.get(gm.graph_id)
        if cached is not None:
            return cached

        total = max(
            sum(
                1
                for _, attrs in gm.graph.nodes(data=True)
                if attrs.get("type") in ELEMENT_TYPES
            ),
            1,
        )

        self._element_counts[gm.graph_id] = total
        return total

    def _collect_paragraphs(self, query_symbols: List[str], symbol_type: str):

        def process_graph(gm):
            local_symbols = Counter()
            local_elements = Counter()

            graph = gm.graph
            total_elements = self._element_count(gm)

            for symbol in query_symbols:

                if symbol not in graph:
                    continue

                if graph.nodes[symbol].get("type") != symbol_type:
                    continue

                neighbours = [
                    neighbor
                    for neighbor in graph.neighbors(symbol)
                    if graph.nodes[neighbor].get("type") in ELEMENT_TYPES
                ]

                if not neighbours:
                    continue

                df = sum(
                    1
                    for neighbor in neighbours
                    if graph.edges[symbol, neighbor].get("type") != "context"
                )
                idf = math.log(1 + total_elements / max(df, 1))
                symbol_id = f"{gm.graph_id}##{symbol}"

                for neighbor in neighbours:
                    edge_type = graph.edges[symbol, neighbor].get("type")
                    weight = CONTEXT_WEIGHT if edge_type == "context" else 1.0

                    local_elements[f"{gm.graph_id}##{neighbor}"] += weight * idf
                    local_symbols[symbol_id] += weight * idf

            return local_elements, local_symbols

        elements_counter = Counter()
        symbols_counter = Counter()

        futures = [self.executor.submit(process_graph, gm) for gm in self.gms]

        for future in futures:
            el_counter, sym_counter = future.result()
            elements_counter.update(el_counter)
            symbols_counter.update(sym_counter)

        return elements_counter, symbols_counter

    # ─────────────────────────────────────────────────────────────

    def _cap_per_table(self, ranked_elements):
        kept = []
        per_table = Counter()

        for full_id, score in ranked_elements:
            graph_id, node_id = full_id.split("##", 1)
            attrs = graph_cache.get(graph_id).graph.nodes[node_id]

            if attrs.get("type") not in ("table_row", "table_cell"):
                kept.append((full_id, score))
                continue

            table_id = (attrs.get("metadata") or {}).get("table_id")
            key = f"{graph_id}##{table_id}"

            if per_table[key] >= MAX_ROWS_PER_TABLE:
                continue

            per_table[key] += 1
            kept.append((full_id, score))

        return kept

    def get_scores(
        self,
        symbol_scores: Dict[str, float],
        element_scores: Dict[str, float],
    ):

        def score_key(item):
            return (-round(item[1], 6), item[0])

        ranked_symbols = sorted(symbol_scores.items(), key=score_key)
        ranked_elements = self._cap_per_table(
            sorted(element_scores.items(), key=score_key)
        )

        if self.max_matches and self.max_matches > 0:
            ranked_symbols = ranked_symbols[: self.max_matches]
            ranked_elements = ranked_elements[: self.max_matches]

        matched_symbols = []
        matched_elements = []

        for full_id, score in ranked_symbols:
            graph_id, symbol = full_id.split("##", 1)
            graph = graph_cache.get(graph_id).graph

            matched_symbols.append({
                "id": symbol,
                "graph_id": graph_id,
                "content": graph.nodes[symbol].get("text"),
                "type": graph.nodes[symbol].get("type"),
                "score": score,
            })

        for full_id, score in ranked_elements:
            graph_id, element = full_id.split("##", 1)
            attrs = graph_cache.get(graph_id).graph.nodes[element]
            metadata = attrs.get("metadata") or {}

            matched_elements.append({
                "id": element,
                "graph_id": graph_id,
                "content": attrs.get("text"),
                "type": attrs.get("type"),
                "metadata": metadata,
                "score": score,
                "row_header": metadata.get("row_header"),
                "col_header": metadata.get("col_header"),
                "table_id": metadata.get("table_id"),
                "page": metadata.get("page"),
            })

        return {
            "elements": matched_elements,
            "symbols": matched_symbols,
        }
