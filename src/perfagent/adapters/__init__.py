from perfagent.adapters.base import BenchmarkAdapter, Instance


def get_adapter(benchmark: str) -> BenchmarkAdapter:
    if benchmark == "gso":
        from perfagent.adapters.gso import GsoAdapter

        return GsoAdapter()
    if benchmark == "swefficiency":
        from perfagent.adapters.swefficiency import SwefficiencyAdapter

        return SwefficiencyAdapter()
    raise ValueError(f"unknown benchmark: {benchmark}")


__all__ = ["BenchmarkAdapter", "Instance", "get_adapter"]
