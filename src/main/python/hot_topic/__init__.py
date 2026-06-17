"""Hot topic discovery module.

Pipeline:
    THUCNews (offline, dev)  ─┐
                              ├─► unified DataFrame ─► BERTopic
    GDELT DOC 2.0 (online) ───┘
"""
__version__ = "0.1.0"
