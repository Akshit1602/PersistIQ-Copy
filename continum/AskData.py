import sys
import continum.AskData as askdata
import continum.AskData.chart_spec as chart_spec
import continum.AskData.growth_simulator as growth_simulator
import continum.AskData.sql_engine as sql_engine
import continum.AskData.visual_generator as visual_generator

sys.modules["continum.AskData"] = askdata
sys.modules["continum.AskData.chart_spec"] = chart_spec
sys.modules["continum.AskData.growth_simulator"] = growth_simulator
sys.modules["continum.AskData.sql_engine"] = sql_engine
sys.modules["continum.AskData.visual_generator"] = visual_generator
