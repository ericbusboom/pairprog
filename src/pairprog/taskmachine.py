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

When you are satisfied that you are ready to begin, submit your analysis and
plan by calling the start_task tool:

    start_task(analysis='< analysis of the task>', plan='<plan>')
"""

    tool_methods = ['start_task']

class PlanStepState(StepState):
    """You are an executive assistant working on executing a plan. You are
reviewing the task plan and deciding how to execute the next step of the plan.

Here is your prior analysis of the task:

```
{task_analysis}
```

Here are the remaining steps in your plan:

```
{plan}
```

{notes_from_last_step}

Instructions
============

Read the task analysis and the plan and decide how to implement the next step.

First, restate the next step of your plan in more detail. The next step should
be self contained, and have one primary output. The next step must fit into one
of the categories listed below.

Next, determine the category of the next step. The categories are:

  * 'execute'. You will run a program by writing a python program, running a shell
    command, or reading and writing files
  * 'research'. You will perform a web search, read documents in the library,
  write document to the library
  * 'analysis'. You will read documents or files, think about them and
    try to answer questions.
  * 'evaluation'. You will assess the quality of your response and determine if
   you have satisfied the user's request
  * 'done' You have determined that you are finished with the user's request.

Then, you will start working on the next step by running the next_step tool:

    next_step(category='<next step category>', detailed_instructions='<detailed task instructions>')
"""

    tool_methods = ['next_step']


class ExecuteStepState(StepState):
    """You are an executive assistant working on executing a plan. You have started
working thorugh the steps you previously decided on. For this step, you will
review the task plan and decide how to execute the next step of the plan, then
you will use the tools available to you to complete the step. You previously
decided that this step would be a {step_type} step, which involves {step_type_description}.

Here is your prior analysis of the task:

```
{{task_analysis}}
```

Here is the detailed description of the task that you are working on now:

```
{{detailed_step}}
```

{step_details}

After completing the step, you will write yourself a note to describe what outputs
the step has, and how to use those outputs in another step.

If you think the step succeeded, you will mark the step complete by calling the step_complete() tool:

    {step_complete_example}

If the step did not succeede, you will mark the step failed by calling the step_failed() tool:

    step_failed(reason='<explaination of why the step failed>', updated_plan='<updated plan>')

Besure to provide all the detail you think is necessary in the `use_note`
or `reason` arguments, because you will use those notes to complete the next step.

"""
    step_type = 'NA'
    step_type_description = "NA"
    tool_methods = ['step_complete', 'step_failed']

    step_complete_example = "step_complete(use_note='<notes on how to use the output>', updated_plan='<updated plan>')"

    def system_message_templ(self):
        """Add a message to the task history"""
        return ExecuteStepState.__doc__.format(
            step_type=self.step_type,
            step_type_description=self.step_type_description,
            step_details=self.__class__.__doc__,
            step_complete_example=self.step_complete_example
        )


class CodeCommandState(ExecuteStepState):
    """For this step, you will execute a code execution step or run a shell command.
You have access to an IPython interpreter, so you can run any python code, and you
can also acess a Bash command line interpreter, so you can run any shell command.
Both the IPyhon and the Bash interpreters have the same working directory, and you can
also perform some basic file system operations. """
    step_type = 'execution'
    step_type_description = "executing python code or running a shell command"

    tool_methods = ExecuteStepState.tool_methods + \
                   ['execute_code', 'shell', 'read_file', 'write_file']


class ResearchState(ExecuteStepState):
    """In the research step, you will perform a web search, read documents in the library,
and write documents to the library. The library is a collection of documents that
are indexed for both vector and term searches. You can directly add documents to the library
from URLs, allowing you to add large documents from the web.

You also have access to wikipedia. The typical Wikipedia use case is to
1) use wikipedia_search to find a page and extract the `store_document_uri`
2) use `store_document_uri` to store the page in the library with store_document
3) use search_documents to find the page in the library

The web_search() function will perform a web search at DuckDuckGo. You can search
for documents, get the URL, then add those documents to the library with store_document.
Then you can search the document with search_documents.

"""

    step_type = 'research'
    step_type_description = "web search, reading documents, writing documents"

    tool_methods = ExecuteStepState.tool_methods + \
                   ['web_search', 'read_file', 'write_file', 'store_document', 'search_documents',
                    'wikipedia_search']


class AnalysisState(ExecuteStepState):
    """For this analysis step, you will read documents, think about them and
try to answer questions. You can read files that you've previously written, or
search the library for documents that you've previously stored. 

When you are done with the analysis, you will write yourself a note to describe what outputs
"""

    step_type = 'analysis'
    step_type_description = "reading documents, thinking, answering questions, and deciding on an answer. "

    step_complete_example = "task_solved(use_note='<notes on how to use the output>', solution='<task_solution>')"

    tool_methods = ExecuteStepState.tool_methods + \
                   ['read_file', 'search_documents']


class EvaluateState(ExecuteStepState):
    """For the evaluation step, you will assess the quality of your response and
determine if you have satisfied the user's request. You can read files that you've
previously written, or search the library for documents that you've previously stored.

Here is your prior analysis of the task:

```
{{task_analysis}}
```

Here is you proposed solution to the task:

```
{{solution}}
```

After evaluating the task, if you determine that the task is complete, you will
tell the user what the solution is, then call the task_done() tool:

    task_done()

 If you determine that the task is not complete, then this step has
 failed, so you will mark the step failed by calling the step_failed() tool:

    step_failed(reason='<explaination of why the step failed>', updated_plan='<updated plan>')

"""

    step_type = 'evaluation'
    step_type_description = "assessing the quality of your response and determining if you have satisfied the user's request"

    tool_methods = ExecuteStepState.tool_methods + \
                   ['read_file', 'search_documents']


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

    next_steps = {
        'execution': CodeCommandState,
        'research': ResearchState,
        'analysis': AnalysisState,
        'evaluation': EvaluateState,
        'done': None
    }

    def start_task(self, analysis: str, plan: str):
        """
        Starts a task with the specified analysis and plan, assigning the task
        analysis and plan to the task manager and transitioning to the next
        state in the task workflow.

        Args:
            analysis (str): A string describing the analysis of the task.
            plan (str): A string outlining the plan for the task.

        Returns:
            None
        """
        self.task_analysis = analysis
        self.plan = plan
        self.next_state(PlanStepState)

    def next_step(self, category: str, detailed_instructions: str):
        """Start the next step"""

        self.step_instructions.append(detailed_instructions)

        if category not in self.next_steps:
            raise ValueError(f"Invalid next step category '{category}'")

        self.step_type = category
        self.next_state(self.next_steps[category])

    def step_complete(self, use_note: str, updated_plan: str = None):
        """Mark the current step complete, noting how to use the outputs from
    the steps, and transition to the next step. Then, update your plan to remove the
    step you just completed. You can also add new steps to your plan, if you think
    that is necessary.

    Args:
        use_note (str): Detailed instructions on how to use the outputs from the step.
        updated_plan (str): (Optional) A revised plan for the remaining steps of the task

    Returns:
        None
    """
        self.step_instructions.append(use_note)
        if updated_plan is not None:
            self.plan = updated_plan
        self.next_state(PlanStepState)

    def task_solved(self, use_note: str, solution: str):
        """Mark the current step complete, and the task as solved, noting how
to use the outputs from the steps, and transition to the next step.
Then formulate the solution, and provide both the solution and the use_note

Args:
    use_note (str): Detailed instructions on how to use the outputs from the step.
    solution (str): The solution to the task

Returns:
    None
"""
        self.step_instructions.append(use_note)
        self.solution = solution
        self.next_state(PlanStepState)

    def task_done(self):
        """Mark the task as done. You should have analyzed and evaluated the
        solution, and determined that the task is complete.
Returns:
None
"""
        self.next_state(StartTaskState)

    def step_failed(self, reason: str, updated_plan: str = None):
        """
Mark the current step as failed, noting the reason for the failure,

Args:
    reason (str): Detailed description of why the step failed, and what you think you need to do to fix it.
    updated_plan (str): (Optional) A revised plan for the remaining steps of the task

Returns:
    None
"""

        self.step_instructions.append(f"ERROR! The last step failed, for this reason: {reason}")
        if updated_plan is not None:
            self.plan = updated_plan
        self.next_state(PlanStepState)


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
