from arcadepy import AsyncArcade
from dotenv import load_dotenv
from google.adk import Agent, Runner
from google.adk.artifacts import InMemoryArtifactService
from google.adk.models.lite_llm import LiteLlm
from google.adk.sessions import InMemorySessionService, Session
from google_adk_arcade.tools import get_arcade_tools
from google.genai import types
from human_in_the_loop import auth_tool, confirm_tool_usage

import os

load_dotenv(override=True)


async def main():
    app_name = "my_agent"
    user_id = os.getenv("ARCADE_USER_ID")

    session_service = InMemorySessionService()
    artifact_service = InMemoryArtifactService()
    client = AsyncArcade()

    agent_tools = await get_arcade_tools(
        client, toolkits=["NotionToolkit"]
    )

    for tool in agent_tools:
        await auth_tool(client, tool_name=tool.name, user_id=user_id)

    agent = Agent(
        model=LiteLlm(model=f"openai/{os.environ["OPENAI_MODEL"]}"),
        name="google_agent",
        instruction="# Introduction
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
        description="An agent that uses NotionToolkit tools provided to perform any task",
        tools=agent_tools,
        before_tool_callback=[confirm_tool_usage],
    )

    session = await session_service.create_session(
        app_name=app_name, user_id=user_id, state={
            "user_id": user_id,
        }
    )
    runner = Runner(
        app_name=app_name,
        agent=agent,
        artifact_service=artifact_service,
        session_service=session_service,
    )

    async def run_prompt(session: Session, new_message: str):
        content = types.Content(
            role='user', parts=[types.Part.from_text(text=new_message)]
        )
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session.id,
            new_message=content,
        ):
            if event.content.parts and event.content.parts[0].text:
                print(f'** {event.author}: {event.content.parts[0].text}')

    while True:
        user_input = input("User: ")
        if user_input.lower() == "exit":
            print("Goodbye!")
            break
        await run_prompt(session, user_input)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())