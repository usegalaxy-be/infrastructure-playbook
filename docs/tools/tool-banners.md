# Tool banners

We can show a message above a tool form, for example to point users to a better tool or to warn about a known problem. Galaxy shows these messages through a webhook, a small script that Galaxy loads into every page. Ours is the `toolmsg` webhook from usegalaxy.eu, deployed by the `pdg.galaxy_webhooks` role.

The same webhook also warns visitors who are not logged in. They see that message above every tool form, in the upload dialog and on the welcome page. Our TPV config rejects jobs from anonymous users, so the message asks them to log in before they upload data or run tools.

All messages live in one file: `inventories/group_vars/galaxyservers/webhooks.yml`. Test and prod share it.

## Add a message to a tool

Each message has three fields:

- `tool_id`: the tool the message is for. The message shows on every tool whose id starts with this text, so leave out the version to cover all versions.
- `class`: the colour, as a Bootstrap alert class. We use `warning` (orange) for recommendations and known problems. `info` (blue), `success`, `danger` and `primary` also work.
- `message`: the text, in HTML. Links to our own tools should start with `/?tool_id=`, so they work on both test and prod.

To find a tool's id, open the tool in Galaxy and copy the `tool_id` value from the address bar, without the version at the end. For tools from the Tool Shed it looks like `toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc`.

For example, to recommend Falco over FastQC, add this under `galaxy_webhooks_toolmsg_messages`:

```yaml
  - tool_id: toolshed.g2.bx.psu.edu/repos/devteam/fastqc/fastqc
    class: warning
    message: >
      <strong>We recommend using <a href="/?tool_id=falco">Falco</a> instead.
      Falco is 3 times faster and offers the same functionality as FastQC.</strong>
```

Before recommending another tool, check that it is installed on prod. A link to a missing tool opens an error page.

## Change the not-logged-in message

The text is `galaxy_webhooks_toolmsg_anonymous_message` in the same file. Set it to an empty string to turn the message off.

## Deploy

Galaxy reads the webhook files only when it starts. A change therefore needs the new file on the server and a restart of the web processes. The `webhooks` tag of `04-galaxy.yml` does exactly that: it writes the webhook files and, if they changed, restarts the two web processes one at a time, so Galaxy stays up. Job handlers keep running.

Run it on test first, then on prod:

```bash
# cd into the worktree
ansible-playbook playbooks/infrastructure/04-galaxy.yml -l test.usegalaxy.be --tags webhooks --check --diff
ansible-playbook playbooks/infrastructure/04-galaxy.yml -l test.usegalaxy.be --tags webhooks
ansible-playbook playbooks/infrastructure/04-galaxy.yml -l usegalaxy.be --tags webhooks --check --diff
ansible-playbook playbooks/infrastructure/04-galaxy.yml -l usegalaxy.be --tags webhooks
```

On prod each web process takes a long time to start, so the restart can run for more than half an hour. The playbook shows no output while it waits.

## Check

Open the tool in Galaxy and look above "Tool Parameters". To see the not-logged-in message, use a private browser window.

To see which script Galaxy serves without opening a browser:

```bash
curl -s https://test.usegalaxy.be/api/webhooks | python3 -c "import json,sys; [print(w['id'], len(w['script'] or '')) for w in json.load(sys.stdin)]"
```

It lists `gtn` (Galaxy's own training button) and `toolmsg`. The length of the `toolmsg` script changes when you add or change a message.
