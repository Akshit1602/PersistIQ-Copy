import argparse
from continum.userui.app import run
p = argparse.ArgumentParser()
p.add_argument("--port",  type=int, default=5050)
p.add_argument("--host",  default="0.0.0.0")
p.add_argument("--data",  default="./sample_data")
p.add_argument("--debug", action="store_true")
a = p.parse_args()
run(host=a.host, port=a.port, data_dir=a.data, debug=a.debug)
