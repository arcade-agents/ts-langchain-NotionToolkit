"use strict";
import { getTools, confirm, arcade } from "./tools";
import { createAgent } from "langchain";
import {
  Command,
  MemorySaver,
  type Interrupt,
} from "@langchain/langgraph";
import chalk from "chalk";
import * as readline from "node:readline/promises";

// configure your own values to customize your agent

// The Arcade User ID identifies who is authorizing each service.
const arcadeUserID = process.env.ARCADE_USER_ID;
if (!arcadeUserID) {
  throw new Error("Missing ARCADE_USER_ID. Add it to your .env file.");
}
// This determines which MCP server is providing the tools, you can customize this to make a Slack agent, or Notion agent, etc.
// all tools from each of these MCP servers will be retrieved from arcade
const toolkits=['NotionToolkit'];
// This determines isolated tools that will be
const isolatedTools=[];
// This determines the maximum number of tool definitions Arcade will return
const toolLimit = 100;
// This prompt defines the behavior of the agent.
const systemPrompt = "# Introduction\nThis AI agent is designed to interact with a Notion workspace, leveraging various tools to manage pages and content efficiently. Its primary purpose is to retrieve, create, and update pages while providing metadata about the workspace and its objects. The agent will operate following a ReAct architecture, enabling it to react to user input dynamically.\n\n# Instructions\n1. **Understand User Intent**: Listen for keywords or phrases that indicate user needs, such as \"create a page,\" \"retrieve content,\" or \"search for a title.\"\n2. **Determine Necessary Actions**: Based on user input, decide which tools to employ to achieve the desired outcome.\n3. **Execute Tool Calls**: Sequentially activate the relevant tools to complete tasks while providing clear output to the user.\n4. **Feedback Loop**: After actions, prompt the user for further instructions or clarification to ensure their needs are met.\n\n# Workflows\n## Workflow 1: Retrieve Page Content by Title\n1. **Listen for user input** requesting page content (e.g., \"Get content for the page titled \u0027Meeting Notes\u0027\").\n2. Use **NotionToolkit_GetPageContentByTitle** to fetch the requested content.\n3. Return the content to the user.\n\n## Workflow 2: Create a New Page\n1. **Listen for a request** to create a new page (e.g., \"Create a new page titled \u0027Project Updates\u0027 under \u0027Projects\u0027\").\n2. Use **NotionToolkit_GetObjectMetadata** with the parent title (\"Projects\") to get the parent page ID.\n3. Use **NotionToolkit_CreatePage** to create the new page with the specified title and optional content.\n4. Confirm the creation with the user.\n\n## Workflow 3: Append Content to an Existing Page\n1. **Listen for instructions** to append content (e.g., \"Append this content to \u0027Weekly Summary\u0027\").\n2. Use **NotionToolkit_GetObjectMetadata** to find the page ID for the specified title.\n3. Use **NotionToolkit_AppendContentToEndOfPage** to append the new content.\n4. Confirm the update with the user.\n\n## Workflow 4: Search for Pages or Databases\n1. **Listen for search queries** (e.g., \"Find all pages related to \u0027Project\u0027\").\n2. Use **NotionToolkit_SearchByTitle** with the user\u0027s query to find relevant pages or databases.\n3. Return a list of matching titles to the user.\n\n## Workflow 5: Get Workspace Structure\n1. **Listen for requests** for workspace information (e.g., \"Show me the structure of my workspace\").\n2. Use **NotionToolkit_GetWorkspaceStructure** to retrieve the workspace layout.\n3. Present the structure to the user.";
// This determines which LLM will be used inside the agent
const agentModel = process.env.OPENAI_MODEL;
if (!agentModel) {
  throw new Error("Missing OPENAI_MODEL. Add it to your .env file.");
}
// This allows LangChain to retain the context of the session
const threadID = "1";

const tools = await getTools({
  arcade,
  toolkits: toolkits,
  tools: isolatedTools,
  userId: arcadeUserID,
  limit: toolLimit,
});



async function handleInterrupt(
  interrupt: Interrupt,
  rl: readline.Interface
): Promise<{ authorized: boolean }> {
  const value = interrupt.value;
  const authorization_required = value.authorization_required;
  const hitl_required = value.hitl_required;
  if (authorization_required) {
    const tool_name = value.tool_name;
    const authorization_response = value.authorization_response;
    console.log("⚙️: Authorization required for tool call", tool_name);
    console.log(
      "⚙️: Please authorize in your browser",
      authorization_response.url
    );
    console.log("⚙️: Waiting for you to complete authorization...");
    try {
      await arcade.auth.waitForCompletion(authorization_response.id);
      console.log("⚙️: Authorization granted. Resuming execution...");
      return { authorized: true };
    } catch (error) {
      console.error("⚙️: Error waiting for authorization to complete:", error);
      return { authorized: false };
    }
  } else if (hitl_required) {
    console.log("⚙️: Human in the loop required for tool call", value.tool_name);
    console.log("⚙️: Please approve the tool call", value.input);
    const approved = await confirm("Do you approve this tool call?", rl);
    return { authorized: approved };
  }
  return { authorized: false };
}

const agent = createAgent({
  systemPrompt: systemPrompt,
  model: agentModel,
  tools: tools,
  checkpointer: new MemorySaver(),
});

async function streamAgent(
  agent: any,
  input: any,
  config: any
): Promise<Interrupt[]> {
  const stream = await agent.stream(input, {
    ...config,
    streamMode: "updates",
  });
  const interrupts: Interrupt[] = [];

  for await (const chunk of stream) {
    if (chunk.__interrupt__) {
      interrupts.push(...(chunk.__interrupt__ as Interrupt[]));
      continue;
    }
    for (const update of Object.values(chunk)) {
      for (const msg of (update as any)?.messages ?? []) {
        console.log("🤖: ", msg.toFormattedString());
      }
    }
  }

  return interrupts;
}

async function main() {
  const config = { configurable: { thread_id: threadID } };
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  console.log(chalk.green("Welcome to the chatbot! Type 'exit' to quit."));
  while (true) {
    const input = await rl.question("> ");
    if (input.toLowerCase() === "exit") {
      break;
    }
    rl.pause();

    try {
      let agentInput: any = {
        messages: [{ role: "user", content: input }],
      };

      // Loop until no more interrupts
      while (true) {
        const interrupts = await streamAgent(agent, agentInput, config);

        if (interrupts.length === 0) {
          break; // No more interrupts, we're done
        }

        // Handle all interrupts
        const decisions: any[] = [];
        for (const interrupt of interrupts) {
          decisions.push(await handleInterrupt(interrupt, rl));
        }

        // Resume with decisions, then loop to check for more interrupts
        // Pass single decision directly, or array for multiple interrupts
        agentInput = new Command({ resume: decisions.length === 1 ? decisions[0] : decisions });
      }
    } catch (error) {
      console.error(error);
    }

    rl.resume();
  }
  console.log(chalk.red("👋 Bye..."));
  process.exit(0);
}

// Run the main function
main().catch((err) => console.error(err));