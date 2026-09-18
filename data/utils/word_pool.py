import builtins
import keyword
import random
import string
import uuid
from enum import Enum

import networkx as nx
from nltk.stem import PorterStemmer
from wordfreq import top_n_list

# will intersect with our programs
BANNED_WORDS = {"counter", "np"}

class WordPoolType(str, Enum):
    ENGLISH = "english"
    SYMBOLIC = "symbolic"
    ADVERSARIAL = "adversarial"
    
_stemmer = PorterStemmer()

def _english_pool(min_len=5):
    raw = top_n_list("en", 50000)
    builtins_set = set(dir(builtins))
    seen_stems = set()
    out = []
    for w in raw:
        if len(w) < min_len:
            continue
        if not w.isidentifier():
            continue
        if keyword.iskeyword(w) or keyword.issoftkeyword(w) or w in builtins_set:
            continue
        if w in BANNED_WORDS:
            continue
        stem = _stemmer.stem(w)
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        out.append(w)
    return out
ENGLISH_WORDS = _english_pool()

def _symbolic_names(n):
    builtins_set = set(dir(builtins))
    out = []
    i = 0
    while len(out) < n:
        s = ""
        x = i
        while True:
            s = string.ascii_lowercase[x % 26] + s
            x = x // 26 - 1
            if x < 0:
                break
        i += 1
        if keyword.iskeyword(s) or keyword.issoftkeyword(s) or s in builtins_set or s in BANNED_WORDS:
            continue
        out.append(s)
    return out


def _adversarial_names(n, rng):
    out = set()
    while len(out) < n:
        s = "_" + uuid.UUID(int=rng.getrandbits(128)).hex[:6]
        out.add(s)
    return list(out)



class WordPool:
    """Pool of `n` unique identifier names, drawn without replacement."""

    def __init__(self, mode, n, rng=None):
        if rng is None:
            rng = random.Random()
        mode = WordPoolType(mode)
        if mode is WordPoolType.ENGLISH:
            if n > len(ENGLISH_WORDS):
                raise ValueError(f"Requested {n} names but only {len(ENGLISH_WORDS)} english names available.")
            names = rng.sample(ENGLISH_WORDS, n)
            
        elif mode is WordPoolType.SYMBOLIC:
            names = _symbolic_names(n)
            
            rng.shuffle(names)
        elif mode is WordPoolType.ADVERSARIAL:
            names = _adversarial_names(n, rng)
            
        else:
            raise ValueError(f"Unknown mode: {mode}")
        
        self._remaining = names

    def __len__(self):
        return len(self._remaining)

    @classmethod
    def sized_for(cls, mode, graphs, rng=None):
        """Build a pool large enough to name every node across `graphs`."""
        n = sum(g.number_of_nodes() for g in graphs)
        return cls(mode, n, rng)

    def sample(self, k):
        if k > len(self._remaining):
            raise ValueError(f"Pool has {len(self._remaining)} names left, requested {k}.")
        out = self._remaining[:k]
        del self._remaining[:k]
        return out

    def relabel(self, G):
        """Relabel one graph; return (new_graph, mapping)."""
        mapping = dict(zip(G.nodes(), self.sample(G.number_of_nodes())))
        return nx.relabel_nodes(G, mapping), mapping

    def relabel_many(self, graphs):
        """Relabel a list of graphs; return (relabeled_list, list_of_mappings)."""
        relabeled, maps = [], []
        for g in graphs:
            g2, m = self.relabel(g)
            relabeled.append(g2)
            maps.append(m)
        return relabeled, maps
