"""Tools for managing a complex set of tasks.

The Task Machine guides an AI on completing a complex task, using various
states, each of which has its own prompts, instructions. and set of tools


"""

def compile_spec(spec: dict):
    o = []

    for e in spec:
        o.append(e['function']['name'])

    return o


import logging
import unittest
from pathlib import Path
from typing import List

from colored import Fore, Back, Style
from typesense import Client

from pairprog.objectstore import ObjectStore
from pairprog.util import generate_tools_specification
from .tool import Tool, PPTools

logger = logging.getLogger(__name__)


def log_system(s):
    return f"{Fore.blue}{s}{Style.reset}"


def log_user(s):
    return f"{Fore.green}{s}{Style.reset}"


def log_state(s):
    return f"{Fore.red}{s}{Style.reset}"

def log_tool(s):
    return f"{Fore.red}{s}{Style.reset}"

def log_spec(s):
    return f"{Fore.yellow}{Back.black}{s}{Style.reset}"


class StepState:
    step_type = 'NA'
    step_type_description = "NA"

    def __init__(self, manager):
        self.manager = manager

    def system_message_templ(self):
        """Add a message to the task history"""
        return self.__class__.__doc__


class StartTaskState(StepState):
    """You are a research assistant with a specialty in web research, programming,
and analysis. You will be given a task by the user, which you will complete
by executing multiple steps.

First determine if you have enough information to answer the user's request,
or to perform the requested task. You may ask the user clarifying questions
until you are satisfied that you understand the problem. Compile
the problem statement and anything you've learned into an analysis statement.

Second, decide what types of tools you will need to complete the task. You can
select from the following categories of tools:

  * 'execute'. You will run a program by writing a python program, running a shell
    command, or reading and writing files
  * 'research'. You will perform a web search, read documents in the library,
  write document to the library, or access wikipedia

You may select zero or more of these tools, each of which is specified in a
list of strings.

When you are satisfied that you are ready to begin, submit your analysis and
plan by calling the start_task tool:

    start_task(analysis='< analysis of the task>', plan='<plan>',
               tools=['<tool1>', '<tool2>', ...])

To recap: follow these steps to complete a task:

1) Ask the user clarifying questions until you are satisfied that you understand the problem.
2) Compile the problem statement and anything you've learned into an analysis statement.
3) Decide what categories of tools you will need to complete the task.
4) Submit your analysis and plan by calling the start_task tool.

"""

    tool_methods = ['start_task']


class ExecuteStepState(StepState):
    """You are currently working on a task for the user.

Here is your prior analysis of the task:

```
{{task_analysis}}
```

Here is your plan for the task:
```
{{plan}}
```

After completing the task, inform the user of the solution, and then mark the
task finished with the task_complete tool:

    task_complete()


"""
    step_type = 'NA'
    step_type_description = "NA"
    tool_methods = ['task_complete']



class TaskManager(PPTools):
    exclude_methods = Tool.exclude_methods + \
                      ['add_message', 'next_state', 'system_message']

    include_methods = []

    user_request: str = None  # The user's request
    task_analysis: str = None  # The analysis of the task
    plan: str = None  # The plan for the task
    solution: str = None  # The solution to the task
    step_type: str = None  # The type of step, only used in execution steps
    step_type_description: str = None

    step_instructions: List[str] = ['']  # The history of detailed step instructions

    messages: List[dict | object] = None  # The history of messages

    current_state: "TaskManagerTool" = None

    def __init__(self, typesense_client: Client, object_store: ObjectStore, working_dir: Path) -> None:
        super().__init__(typesense_client, object_store, working_dir)

        self.next_state(StartTaskState)

    def system_message(self):
        """Add a message to the task history"""
        templ = self.current_state.system_message_templ()

        if self.step_instructions and self.step_instructions[-1]:
            nfls = self.step_instructions[-1]
            notes_from_last_step = f"Note from your last step\n```\n{nfls}\n```"
        else:
            nfls = ''
            notes_from_last_step = ''

        # repalce any double curly braces with single curly braces

        templ = templ.replace('{{', '{').replace('}}', '}')

        sm = templ.format(
            task_analysis=self.task_analysis,
            plan=self.plan,
            notes_from_last_step=notes_from_last_step,
            step_type=self.current_state.step_type,
            step_type_description=self.current_state.step_type_description,
            detailed_step=nfls,
            solution=self.solution
        )

        logger.info(log_system(sm))

        return sm

    def specification(self):
        """Return the specification for the tools available in this class."""
        spec = generate_tools_specification(self.__class__,
                                            include_methods=self.current_state.tool_methods)

        logger.info(log_spec(f"Specification: {compile_spec(spec)}"))

        return spec

    def next_state(self, state: type):
        """Start the next step"""

        # if the state is a class, instantiate it
        if isinstance(state, type):
            state = state(self)

        self.current_state = state
        self.include_methods = state.tool_methods

        logger.info(log_state(f"Next state: {state.__class__.__name__}"))


    def start_task(self, analysis: str, plan: str, tools: list[str]):
        """
        Starts a task with the specified analysis and plan, assigning the task
        analysis and plan to the task manager and transitioning to the next
        state in the task workflow.

        Args:
            analysis (str): A string describing the analysis of the task.
            plan (str): A string outlining the plan for the task.
            tools (list[str]): A list of strings specifying the categories of tools to be used
                in the task.

        Returns:
            None
        """

        tool_sets = {
            'execute': ['execute_code', 'execute_shell', 'read_file', 'write_file', 'read_library', 'write_library'],
            'research': ['web_search', 'read_library', 'write_library', 'read_wikipedia', 'store_document','read_document']
        }

        tools = [t for t in tools if t in tool_sets.keys()]

        if not tools:
            raise ValueError(f"You must select some tool groups: {tools}")

        self.task_analysis = analysis
        self.include_methods = list(set(tools))
        self.plan = plan
        self.next_state(ExecuteStepState)

        logger.info(log_tool(f"Start Task:\nAnalysis: {analysis}\nPlan: {plan}\nTools: {self.include_methods}"))

    def task_complete(self):
        """Mark the current task complete,
    """

        logger.info(log_tool(f"Complete Task"))
        self.include_methods = ['start_task']
        self.next_state(StartTaskState)


class TMTestCase(unittest.TestCase):

    def test_basic(self):
        tm = TaskManager(None, None, Path.cwd())

        ##
        ## Start Task State
        self.assertIsInstance(tm.current_state, StartTaskState)

        tm.run_tool('start_task', {"analysis": "analysis", "plan": "plan"})

        ##
        ## Plan Step State
        self.assertIsInstance(tm.current_state, PlanStepState)

        with self.assertRaises(NotImplementedError):
            tm.run_tool('start_task', {"analysis": "analysis", "plan": "1) plan\n2) plan\n3) More Plan"})

        tm.run_tool('next_step',
                    {"category": "execution", "detailed_instructions": "Detailed instructions about this step"})

        ##
        ## Execute Step State
        self.assertIsInstance(tm.current_state, CodeCommandState)

        self.assertIn('execute_code', compile_spec(tm.specification()))
        x = tm.run_tool('execute_code', {"code": "x=1\nx"})
        self.assertEqual(1, x)

        self.assertIn("Detailed instructions about this step", tm.system_message())

        ##
        ## Complete the step successfully, and transition to the Plan Step
        tm.run_tool('step_complete', {"use_note": "Use the output of this step in the next step",
                                      "updated_plan": "2) plan\n3) More Plan"})

        self.assertIsInstance(tm.current_state, PlanStepState)

        # Start next step, Research
        tm.run_tool('next_step',
                    {"category": "research", "detailed_instructions": "Do some research"})

        ##
        ## Execute Step State, ResearchState
        self.assertIsInstance(tm.current_state, ResearchState)
        self.assertIn("step_complete(use_note", tm.system_message())

        ##
        ## Step Failed, back to Plan
        tm.run_tool('step_failed', {"reason": "I failed", "updated_plan": "2) plan\n3) More Plan"})
        print(tm.system_message())

        # Start next step, Research
        tm.run_tool('next_step',
                    {"category": "analysis", "detailed_instructions": "Time to analyze"})

        ##
        ## Analysis Step State
        self.assertIsInstance(tm.current_state, AnalysisState)
        self.assertIn("task_solved(use_note", tm.system_message())


if __name__ == "__main__":
    unittest.main()
