from freegenius import getDeviceInfo, showErrors, get_or_create_collection, query_vectors, toGeminiMessages, executeToolFunction, extractPythonCode
from freegenius import config
import traceback, os
from typing import Optional, List, Dict, Union
import vertexai
from vertexai.preview.generative_models import GenerativeModel, FunctionDeclaration, Tool
from vertexai.generative_models._generative_models import (
    GenerationConfig,
    HarmCategory,
    HarmBlockThreshold,
)

class CallGemini:

    @staticmethod
    def checkCompletion():
        if os.environ["GOOGLE_APPLICATION_CREDENTIALS"] and "Vertex AI" in config.enabledGoogleAPIs:
            config.geminipro_model = GenerativeModel("gemini-pro")
        else:
            print("Vertex AI is disabled!")
            print("Read https://github.com/eliranwong/letmedoit/wiki/Google-API-Setup for setting up Google API.")
        # initiation
        vertexai.init()
        
        config.geminipro_generation_config=GenerationConfig(
            temperature=config.llmTemperature, # 0.0-1.0; default 0.9
            max_output_tokens=config.geminipro_max_output_tokens, # default
            candidate_count=1,
        )
        # Note: BLOCK_NONE is not allowed
        config.geminipro_safety_settings={
            HarmCategory.HARM_CATEGORY_UNSPECIFIED: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        }

    @staticmethod
    def autoHealPythonCode(code, trace):
        ...

    @staticmethod
    def regularCall(messages: dict, useSystemMessage: bool=True, **kwargs):
        history, systemMessage, lastUserMessage = toGeminiMessages(messages=messages)
        userMessage = f"{systemMessage}\n\nHere is my request:\n{lastUserMessage}" if useSystemMessage and systemMessage else lastUserMessage
        chat = config.geminipro_model.start_chat(history=history)
        return chat.send_message(
            userMessage,
            generation_config=config.geminipro_generation_config,
            safety_settings=config.geminipro_safety_settings,
            stream=True,
            **kwargs,
        )

    @staticmethod
    def getResponseDict(history: list, schema: dict, userMessage: str, **kwargs) -> dict:
        name, description, parameters = schema["name"], schema["description"], schema["parameters"]
        chat = config.geminipro_model.start_chat(history=history)
        # declare a function
        function_declaration = FunctionDeclaration(
            name=name,
            description=description,
            parameters=parameters,
        )
        tool = Tool(
            function_declarations=[function_declaration],
        )
        try:
            completion = chat.send_message(
                userMessage,
                generation_config=config.geminipro_generation_config,
                safety_settings=config.geminipro_safety_settings,
                tools=[tool],
                stream=False,
                **kwargs,
            )
            responseDict = dict(completion.candidates[0].content.parts[0].function_call.args)
            #if config.developer:
            #    import pprint
            #    pprint.pprint(responseDict)
            return responseDict
        except:
            showErrors()
            return {}

    @staticmethod
    def getSingleChatResponse(userInput: str, history: Optional[list]=None, **kwargs) -> str:
        # non-streaming single call
        try:
            chat = config.geminipro_model.start_chat(history=history)
            completion = chat.send_message(
                userInput,
                generation_config=config.geminipro_generation_config,
                safety_settings=config.geminipro_safety_settings,
                stream=False,
                **kwargs,
            )
            return completion.candidates[0].content.parts[0].text
        except:
            return ""

    # Specific Function Call equivalence

    @staticmethod
    def runSingleFunctionCall(messages: list, function_name: str) -> list:
        messagesCopy = messages[:]
        try:
            _, function_call_response = CallGemini.getSingleFunctionCallResponse(messages, function_name)
            function_call_response = function_call_response if function_call_response else config.tempContent
            messages[-1]["content"] += f"""\n\nAvailable information:\n{function_call_response}"""
            config.tempContent = ""
        except:
            showErrors()
            return messagesCopy
        return messages

    @staticmethod
    def getSingleFunctionCallResponse(messages: list, function_name: str, **kwargs) -> List[Union[Dict, str]]:
        tool_schema = config.toolFunctionSchemas[function_name]
        user_request = messages[-1]["content"]
        func_arguments = CallGemini.extractToolParameters(schema=tool_schema, userInput=user_request, ongoingMessages=messages, **kwargs)
        function_call_response = executeToolFunction(func_arguments=func_arguments, function_name=function_name)
        function_call_message_mini = {
            "role": "assistant",
            "content": "",
            "function_call": {
                "name": function_name,
                "arguments": func_arguments,
            }
        }
        return function_call_message_mini, function_call_response

    # Auto Function Call equivalence

    @staticmethod
    def runAutoFunctionCall(messages: dict, noFunctionCall: bool = False):
        user_request = messages[-1]["content"]
        if config.intent_screening:
            # 1. Intent Screening
            if config.developer:
                config.print("screening ...")
            noFunctionCall = True if noFunctionCall else CallGemini.screen_user_request(messages=messages, user_request=user_request)
        if noFunctionCall:
            return CallGemini.regularCall(messages)
        else:
            # 2. Tool Selection
            if config.developer:
                config.print("selecting tool ...")
            tool_collection = get_or_create_collection("tools")
            search_result = query_vectors(tool_collection, user_request)
            if not search_result:
                # no tool is available; return a regular call instead
                return CallGemini.regularCall(messages)
            semantic_distance = search_result["distances"][0][0]
            if semantic_distance > config.tool_dependence:
                return CallGemini.regularCall(messages)
            metadatas = search_result["metadatas"][0][0]
            tool_name = metadatas["name"]
            tool_schema = config.toolFunctionSchemas[tool_name]
            if config.developer:
                config.print3(f"Selected: {tool_name} ({semantic_distance})")
            # 3. Parameter Extraction
            if config.developer:
                config.print("extracting parameters ...")
            try:
                tool_parameters = CallGemini.extractToolParameters(schema=tool_schema, userInput=user_request, ongoingMessages=messages)
                # 4. Function Execution
                tool_response = executeToolFunction(func_arguments=tool_parameters, function_name=tool_name)
            except:
                print(traceback.format_exc())
                tool_response = "[INVALID]"
            # 5. Chat Extension
            if tool_response == "[INVALID]":
                # invalid tool call; return a regular call instead
                return CallGemini.regularCall(messages)
            elif tool_response:
                if config.developer:
                    config.print2(config.divider)
                    config.print2("Tool output:")
                    print(tool_response)
                    config.print2(config.divider)
                messages[-1]["content"] = f"""Describe the query and response below in your own words in detail, without comment about your ability.

My query:
{user_request}

Your response:
{tool_response}"""
                return CallGemini.regularCall(messages)
            else:
                # tool function executed without chat extension
                config.currentMessages.append({"role": "assistant", "content": "Done!"})
                return None

    @staticmethod
    def screen_user_request(messages: dict, user_request: str) -> bool:
        
        deviceInfo = f"""\n\nMy device information:\n{getDeviceInfo()}""" if config.includeDeviceInfoInContext else ""
        properties = {
            "answer": {
                "type": "string",
                "description": """Evaluate my request to determine if you are able to resolve my request as a text-based AI:
- Answer 'no' if you are asked to execute a computing task or an online search.
- Answer 'no' if you are asked for updates / news / real-time information.
- Answer 'yes' if the request is a greeting or translation.
- Answer 'yes' only if you have full information to give a direct response.""",
                "enum": ['yes', 'no'],
            },
        }
        schema = {
            "name": "screen_user_request",
            "description": f'''Estimate user request''',
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": ["code"],
            },
        }
        userMessage = f"""Answer either 'yes' or 'no', to tell if you are able to resolve my request below as a text-based AI:

<request>
{user_request}{deviceInfo}
</request>"""

        history, *_ = toGeminiMessages(messages=messages)

        output = CallGemini.getResponseDict(history, schema=schema, userMessage=userMessage)
        return True if "yes" in str(output).lower() else False

    @staticmethod
    def extractToolParameters(schema: dict, userInput: str, ongoingMessages: list = [], **kwargs) -> dict:
        """
        Extract action parameters
        """

        history, _, lastUserMessage = toGeminiMessages(messages=ongoingMessages)

        deviceInfo = f"""

Here is my device information for additional reference:
<my_device_information>
{getDeviceInfo()}
</my_device_information>""" if config.includeDeviceInfoInContext else ""

        # Generate Code when required
        if "code" in schema["parameters"]["required"]:
            enforceCodeOutput = """ Remember, you should format the requested information, if any, into a string that is easily readable by humans. Use the 'print' function in the final line to display the requested information."""
            schema["parameters"]["properties"]["code"]["description"] += enforceCodeOutput
            code_instruction = f"""Generate python code according to the following instruction:
</instruction>
{schema["parameters"]["properties"]["code"]["description"]}
</instruction>

Here is my request:
<request>
{userInput}
</request>{deviceInfo}

Remember, response with the required python code ONLY, WITHOUT extra notes or explanations."""
            code = CallGemini.getSingleChatResponse(code_instruction, history=history)
            if len(schema["parameters"]["properties"]) == 1:
                if code := extractPythonCode(code):
                    return {"code": code}
            code = f"""The required code is given below:
<code>
{code}
</code>"""
            code = code.replace(r"\\n", "\n")
        else:
            code = ""
        
        userMessage = f"""<request>
{lastUserMessage}
</request>{deviceInfo}{code}

When necessary, generate content based on your knowledge."""

        parameters = CallGemini.getResponseDict(history=history, schema=schema, userMessage=userMessage, **kwargs)
        # fix linebreak
        if code:
            parameters["code"] = parameters["code"].replace("\\n", "\n")
        return parameters