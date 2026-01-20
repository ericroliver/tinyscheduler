We have a basic team based agentic system. 

1. We use goose and the goose feature https://block.github.io/goose/docs/guides/recipes/ as our core work flow engine
2. We use an mcp server called tinytask-mcp to manage a task as it flows through the agents. https://github.com/ericroliver/tinytask-mcp
3. We have several different receiptes defined and we will add more
    - Dispatcher: reads the user request, creates a task in tinytask, decides where to dispatch the task first and assigns the task the that queue
    - Architect: creates technical specifications for a user request that is about creating a new feature etc.
    - Product: writes product stories for the user request/technical documents
    - devops: Github/Gitlab, etc. administrator, creates repos, issues, etc. Depends on the infrastructure in use

A new _user request appears in a folder name {{base_path}}/inbound
- The dispatcher reads _user requests in this folder, creates tasks, moves the task files(s) to {{base_path}}/workqueue/task_{id}
- the Dispatcher moves the new task to the first agent (say the architect for this example).
- you can say that the path for a task is {{base_path}}/workqueue/task_{id}. All files for the task live in this folder.
- The architect determines what project the _user request is for. If it is a new project the architect creates base docs as well as the _technical doc required to satisfy the user request.
- Once the architect is complete, the agent moves the task to the product queue.
- Product reads the docs in the task folder, breaks the work down into stories and creates story docs for each story. Product also creates and index document that is an overview of all documentation
- Product moves the task to the 'devops' agent so the agent can create a repo if required, then create issues for each story
- The devops agent moves the task to the 'coder' queue.
- the coder agents work from the issues but also carry story updates back to the task

We use model context protocol servers to allow the agents to perform the work
- system tools: file manipulation and reading and writing files
- tinytask-mcp: task management
- Github-mcp: ability to interact with github. repos maintenance, issue maintenance, prs, code reviews etc.

Currently we have been testing with commands like so:

```
goose run --recipe /home/user/workspace/calypso/recipes/architect.yaml --params base_path="/home/user/workspace/calypso" --provider openai --model gpt-5.2 --no-session

goose run --recipe /home/user/workspace/calypso/recipes/product.yaml --params base_path="/home/user/workspace/calypso" --provider anthropic --model claude-sonnet-4-5 --no-session
```

Currently we run these commands manually when we know there is a task in a specific agent queue. I envision a python script that runs from a cron job and:

1) queries for idle tasks across all agent queues using the mcp tools
2) spawns a goose sub process for all agents
    - for instance, if 4 tasks come back, 2 for architect and 2 for blogger, then we only spawn two processes. one with the architect recipe and one for the blogger recipe

Here is where it gets interesting, we want a simple way to keep track of these running processes. perhaps we could write a file to a 'running_tasks' folder where the name of the file is 'task_{id}.pid' and the file contains the process id.

Eventually we will want to be sophisticated with regard to keeping track of running processes and detecting orphans etc. Really feels like a simple file tracking with defined roles that write and everyone else reads could get us there. We would iterate this folder and that gives us the task_id/process_id pair, we can then interogate the process and query tinytask for task information.

But this is an area we really need to explore further.


