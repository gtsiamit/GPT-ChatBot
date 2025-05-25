from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, get_buffer_string, trim_messages
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
import tiktoken
from typing import Dict


class ChatBot:

    def __init__(self, model_name="gpt-4.1-nano-2025-04-14", thread_id="thread_id"):
        # Initialize the chatbot with a model and thread ID

        # Store the thread ID in an instance variable
        self.thread_id = thread_id

        # Configuration for the chatbot, including the thread ID
        self.config = {"configurable": {"thread_id": self.thread_id}}

        # Initialize the chat model with the specified model name
        self.model = init_chat_model(model_name, model_provider="openai")

        # Define the prompt template for the chatbot
        self.prompt_template = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a useful assistant. Answer the questions. Be brief in your responses.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        # Define a trimmer to manage the length of messages
        self.trimmer = self._define_trimmer()

        # Build the state graph for the chatbot
        self.graph = self._build_graph()

    def _token_counter(self, messages: list) -> int:
        """
        Count the number of tokens in a list of messages.

        Args:
            messages (list): A list of messages to count tokens in.

        Returns:
            int: The total number of tokens in the messages.
        """

        # Use the tiktoken library to count tokens in the messages
        enc = tiktoken.get_encoding("cl100k_base")
        # Convert the messages to a string representation
        text = get_buffer_string(messages)
        # Encode the text to count the tokens
        return len(enc.encode(text))

    def _define_trimmer(self):
        """
        Define a trimmer to manage the length of messages.

        Returns:

            langchain_core.runnables.base.RunnableLambda: A runnable that trims messages based on token count.
        """
        return trim_messages(
            max_tokens=100,
            strategy="last",
            token_counter=self._token_counter,
            include_system=True,
            allow_partial=False,
            start_on="human",
        )

    def _call_model(self, state: MessagesState) -> Dict:
        """
        Call the chat model with the current state of messages.

        Args:
            state (MessagesState): The current state containing messages.

        Returns:
            Dict: A dictionary containing the model's response.
        """

        # Trim the messages to fit within the token limit and prepare the prompt
        trimmed_messages = self.trimmer.invoke(state["messages"])
        prompt = self.prompt_template.invoke({"messages": trimmed_messages})

        # Invoke the chat model with the prepared prompt
        response = self.model.invoke(prompt)

        return {"messages": [response]}

    def _build_graph(self) -> CompiledStateGraph:
        """
        Build the state graph for the chatbot.

        Returns:
            langgraph.graph.StateGraph: The compiled state graph for the chatbot.
        """

        # Create a state graph with the defined state schema
        workflow = StateGraph(state_schema=MessagesState)
        workflow.add_edge(START, "model")
        workflow.add_node("model", self._call_model)

        # Add memory saving functionality to the workflow
        memory = MemorySaver()

        # Return the compiled workflow with memory checkpointing
        return workflow.compile(checkpointer=memory)

    def invoke(self, input_prompt: str) -> str:
        """
        Invoke the chatbot with user input and return the model's response.

        Args:
            input_prompt (str): The input from the user to the chatbot.

        Returns:
            str: The response from the chatbot model.
        """

        # Convert the input prompt into a HumanMessage and invoke the graph
        input_messages = [HumanMessage(input_prompt)]
        output = self.graph.invoke({"messages": input_messages}, self.config)

        # Return the content of the last message in the output
        return output["messages"][-1].content
