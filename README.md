# darktan-toolbox
<img width="512" height="447" alt="darktan_toolbox_logo" src="https://github.com/user-attachments/assets/5cdd359a-4371-43dd-95ea-bbd97ec6244c" />

A collection of Python scripts for various production-related tasks, including bulk video conversion, archive extraction, file rearrangement, and PSD manipulation.
Some scripts are very specific and only useful for the production they were created for. This repository mainly serves as a backup of various scripts and snippets, which may be slightly modified in the future to make these tools more universal.

Python 3.1 or higher is required on the machines.


For Windows 10 :

setx PATH "%PATH%;C:\Users\yourusername\bin"

check with :
echo %PATH%

The "bin" folder contains shims to the scripts, like this :

import runpy, sys
sys.argv = [r"B:\app\scripts\darktan.py"] + sys.argv[1:]
runpy.run_path(r"B:\app\scripts\darktan.py", run_name="__main__")

Scripts and shims can be managed with darktan.py

darktan list
for showing all the scripts installed

<img width="358" height="115" alt="image" src="https://github.com/user-attachments/assets/a5635495-567c-460b-985f-0edbab905073" />

//WIP - edit later
