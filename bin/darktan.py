import runpy, sys
sys.argv = [r"B:\app\scripts\darktan.py"] + sys.argv[1:]
runpy.run_path(r"B:\app\scripts\darktan.py", run_name="__main__")
