
"""Names and constants of the remake shared by every layer (pure data, imports nothing above it).

The game model (``game``), the logic, the patches and the tracker all name the same
actors, items and saved flags: those names live here so that no lower layer has to
import a patch module to know them.
"""
