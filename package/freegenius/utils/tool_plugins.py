from freegenius import config, getLocalStorage, get_or_create_collection, add_vector, fileNamesWithoutExtension
from freegenius import print1, print2, print3
from pathlib import Path
from chromadb.config import Settings
import os, shutil, chromadb, json
from typing import Callable


from freegenius import config, getLocalStorage, execPythonFile
import os

class Plugins:

    @staticmethod
    def runPlugins():        
        storageDir = getLocalStorage()
        # The following config values can be modified with plugins, to extend functionalities
        #config.pluginsWithFunctionCall = []
        config.aliases = {}
        config.predefinedContexts = {
            "[none]": "",
            "[custom]": "",
        }
        config.predefinedInstructions = {}
        config.inputSuggestions = []
        config.outputTransformers = []
        config.toolFunctionSchemas = {}
        config.toolFunctionMethods = {}

        pluginFolder = os.path.join(config.freeGeniusAIFolder, "plugins")
        if storageDir:
            customPluginFoler = os.path.join(storageDir, "plugins")
            Path(customPluginFoler).mkdir(parents=True, exist_ok=True)
            pluginFolders = (pluginFolder, customPluginFoler)
        else:
            pluginFolders = (pluginFolder,)
        # always run 'integrate google searches'
        internetSeraches = "integrate google searches"
        script = os.path.join(pluginFolder, "{0}.py".format(internetSeraches))
        execPythonFile(script)
        # always include the following plugins
        requiredPlugins = (
            "auto heal python code",
            "execute python code",
            "execute termux command",
        )
        for i in requiredPlugins:
            if i in config.pluginExcludeList:
                config.pluginExcludeList.remove(i)
        # execute enabled plugins
        for folder in pluginFolders:
            for plugin in fileNamesWithoutExtension(folder, "py"):
                if not plugin in config.pluginExcludeList:
                    script = os.path.join(folder, "{0}.py".format(plugin))
                    run = execPythonFile(script)
                    if not run:
                        config.pluginExcludeList.append(plugin)
        if internetSeraches in config.pluginExcludeList:
            del config.toolFunctionSchemas["integrate_google_searches"]
        for i in config.toolFunctionMethods:
            if not i in ("python_qa",):
                callEntry = f"[CALL_{i}]"
                if not callEntry in config.inputSuggestions:
                    config.inputSuggestions.append(callEntry)

    # integrate function call plugin
    @staticmethod
    def addFunctionCall(signature: str, method: Callable[[dict], str]):
        name = signature["name"]
        config.toolFunctionSchemas[name] = {key: value for key, value in signature.items() if not key in ("intent", "examples")}
        config.toolFunctionMethods[name] = method
        ToolStore.add_tool(signature)

class ToolStore:

    @staticmethod
    def setupToolStoreClient():
        tool_store = os.path.join(getLocalStorage(), "tool_store")
        try:
            shutil.rmtree(tool_store, ignore_errors=True)
            print2("Old tool store removed!")
        except:
            print2("Failed to remove old tool store!")
        Path(tool_store).mkdir(parents=True, exist_ok=True)
        config.tool_store_client = chromadb.PersistentClient(tool_store, Settings(anonymized_telemetry=False))

    @staticmethod
    def add_tool(signature):
        name, description, parameters = signature["name"], signature["description"], signature["parameters"]
        print(f"Adding tool: {name}")
        if "examples" in signature:
            description = description + "\n" + "\n".join(signature["examples"])
        collection = get_or_create_collection("tools")
        metadata = {
            "name": name,
            "parameters": json.dumps(parameters),
        }
        add_vector(collection, description, metadata)