"""src/watcher — Pipeline surec denetcisi.

Deterministik kontroller (LLM'siz):
    check_parse(data)    -> List[Finding]
    check_nest(data)     -> List[Finding]
    check_price(data)    -> List[Finding]
    check_priority(data) -> List[Finding]

LLM anlatim (opsiyonel):
    WatcherRole.narrate(findings) -> WatcherResult

Kullanim:
    from src.watcher.checks import check_nest, check_price, Finding
    from src.watcher.thresholds import WatcherThresholds
"""
