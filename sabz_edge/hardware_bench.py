"""Explicit opt-in LOW-VOLTAGE bench service. Never use on road lamp circuits."""
import argparse
from dataclasses import replace
from .server import Settings,run
from .store import InstanceLock
from .serial_bench import SerialBenchAdapter
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--low-voltage-bench-only',required=True,action='store_true')
    args=p.parse_args()
    settings=Settings()
    settings.timing=replace(settings.timing,require_metric_protection=True)
    Path(settings.state_path).parent.mkdir(parents=True,exist_ok=True)
    with InstanceLock(settings.state_path+'.lock'):
        run(settings,adapter_factory=lambda timing:SerialBenchAdapter(timing,port=args.port))

if __name__=='__main__':main()
