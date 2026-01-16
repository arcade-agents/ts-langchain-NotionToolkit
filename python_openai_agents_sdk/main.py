from agents import (Agent, Runner, AgentHooks, Tool, RunContextWrapper,
                    TResponseInputItem,)
from functools import partial
from arcadepy import AsyncArcade
from agents_arcade import get_arcade_tools
from typing import Any
from human_in_the_loop import (UserDeniedToolCall,
                               confirm_tool_usage,
                               auth_tool)

import globals


class CustomAgentHooks(AgentHooks):
    def __init__(self, display_name: str):
        self.event_counter = 0
        self.display_name = display_name

    async def on_start(self,
                       context: RunContextWrapper,
                       agent: Agent) -> None:
        self.event_counter += 1
        print(f"### ({self.display_name}) {
              self.event_counter}: Agent {agent.name} started")

    async def on_end(self,
                     context: RunContextWrapper,
                     agent: Agent,
                     output: Any) -> None:
        self.event_counter += 1
        print(
            f"### ({self.display_name}) {self.event_counter}: Agent {
                # agent.name} ended with output {output}"
                agent.name} ended"
        )

    async def on_handoff(self,
                         context: RunContextWrapper,
                         agent: Agent,
                         source: Agent) -> None:
        self.event_counter += 1
        print(
            f"### ({self.display_name}) {self.event_counter}: Agent {
                source.name} handed off to {agent.name}"
        )

    async def on_tool_start(self,
                            context: RunContextWrapper,
                            agent: Agent,
                            tool: Tool) -> None:
        self.event_counter += 1
        print(
            f"### ({self.display_name}) {self.event_counter}:"
            f" Agent {agent.name} started tool {tool.name}"
            f" with context: {context.context}"
        )

    async def on_tool_end(self,
                          context: RunContextWrapper,
                          agent: Agent,
                          tool: Tool,
                          result: str) -> None:
        self.event_counter += 1
        print(
            f"### ({self.display_name}) {self.event_counter}: Agent {
                # agent.name} ended tool {tool.name} with result {result}"
                agent.name} ended tool {tool.name}"
        )


async def main():

    context = {
        "user_id": os.getenv("ARCADE_USER_ID"),
    }

    client = AsyncArcade()

    arcade_tools = await get_arcade_tools(
        client, toolkits=["NotionToolkit"]
    )

    for tool in arcade_tools:
        # - human in the loop
        if tool.name in ENFORCE_HUMAN_CONFIRMATION:
            tool.on_invoke_tool = partial(
                confirm_tool_usage,
                tool_name=tool.name,
                callback=tool.on_invoke_tool,
            )
        # - auth
        await auth_tool(client, tool.name, user_id=context["user_id"])

    agent = Agent(
        name="",
        instructions="# Introduction
This AI agent is designed to interact with a Notion workspace, leveraging various tools to manage pages and content efficiently. Its primary purpose is to retrieve, create, and update pages while providing metadata about the workspace and its objects. The agent will operate following a ReAct architecture, enabling it to react to user input dynamically.

# Instructions
1. **Understand User Intent**: Listen for keywords or phrases that indicate user needs, such as "create a page," "retrieve content," or "search for a title."
2. **Determine Necessary Actions**: Based on user input, decide which tools to employ to achieve the desired outcome.
3. **Execute Tool Calls**: Sequentially activate the relevant tools to complete tasks while providing clear output to the user.
4. **Feedback Loop**: After actions, prompt the user for further instructions or clarification to ensure their needs are met.

# Workflows
## Workflow 1: Retrieve Page Content by Title
1. **Listen for user input** requesting page content (e.g., "Get content for the page titled 'Meeting Notes'").
2. Use **NotionToolkit_GetPageContentByTitle** to fetch the requested content.
3. Return the content to the user.

## Workflow 2: Create a New Page
1. **Listen for a request** to create a new page (e.g., "Create a new page titled 'Project Updates' under 'Projects'").
2. Use **NotionToolkit_GetObjectMetadata** with the parent title ("Projects") to get the parent page ID.
3. Use **NotionToolkit_CreatePage** to create the new page with the specified title and optional content.
4. Confirm the creation with the user.

## Workflow 3: Append Content to an Existing Page
1. **Listen for instructions** to append content (e.g., "Append this content to 'Weekly Summary'").
2. Use **NotionToolkit_GetObjectMetadata** to find the page ID for the specified title.
3. Use **NotionToolkit_AppendContentToEndOfPage** to append the new content.
4. Confirm the update with the user.

## Workflow 4: Search for Pages or Databases
1. **Listen for search queries** (e.g., "Find all pages related to 'Project'").
2. Use **NotionToolkit_SearchByTitle** with the user's query to find relevant pages or databases.
3. Return a list of matching titles to the user.

## Workflow 5: Get Workspace Structure
1. **Listen for requests** for workspace information (e.g., "Show me the structure of my workspace").
2. Use **NotionToolkit_GetWorkspaceStructure** to retrieve the workspace layout.
3. Present the structure to the user.",
        model=os.environ["OPENAI_MODEL"],
        tools=arcade_tools,
        hooks=CustomAgentHooks(display_name="")
    )

    # initialize the conversation
    history: list[TResponseInputItem] = []
    # run the loop!
    while True:
        prompt = input("You: ")
        if prompt.lower() == "exit":
            break
        history.append({"role": "user", "content": prompt})
        try:
            result = await Runner.run(
                starting_agent=agent,
                input=history,
                context=context
            )
            history = result.to_input_list()
            print(result.final_output)
        except UserDeniedToolCall as e:
            history.extend([
                {"role": "assistant",
                 "content": f"Please confirm the call to {e.tool_name}"},
                {"role": "user",
                 "content": "I changed my mind, please don't do it!"},
                {"role": "assistant",
                 "content": f"Sure, I cancelled the call to {e.tool_name}."
                 " What else can I do for you today?"
                 },
            ])
            print(history[-1]["content"])

if __name__ == "__main__":
    import asyncio

    asyncio.run(main())