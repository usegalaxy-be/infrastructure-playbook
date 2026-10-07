This Ansible role is for automated installation and testing of tools from a Tool Shed into
Galaxy.

When run, this role will create an execution environment, install
[ephemeris](https://github.com/galaxyproject/ephemeris) for tool installation and
[galaxy-tool-util](https://pypi.org/project/galaxy-tool-util/) for tool testing, and invoke the
shed-install command to install desired tools into Galaxy, followed by testing with galaxy-tool-test.
The list of tools to install is provided in `files/tool_list.yaml` file.

Usage
-----
To use the role, you need to create a playbook and include the role in it. A
sample playbook is available [here](https://github.com/afgane/galaxy-tools-playbook)
that will get you up and running in minutes.

Variables
---------
### Required variables ###
Only one of the two variables is requried (if both are set, the API key
takes precedence and a bootstrap user is not created):
- `galaxy_singularity_user_api_key`: the Galaxy API key for an admin user on the target
  Galaxy instance (not required if the bootstrap user is being created)
- `galaxy_tools_admin_user_password`: a password for the Galaxy bootstrap user
  (required only if `galaxy_install_bootstrap_user` variable is set)

### Optional variables ###
See `defaults/main.yml` for the available variables and their defaults.

New variables for testing:
- `galaxy_tool_util_venv_dir`: Virtual environment directory for galaxy-tool-util (default: "{{ tool_install_dir }}/galaxy_tool_util_venv")
- `galaxy_conda_user_api_key`: API key for Conda-only user (for resubmitting failed tests)
- `sqlite_db_path`: Path to SQLite database with installed tools (default: "{{ tool_install_dir }}/installed_tools.db")
- `test_tools_since_date`: Date filter for `since_date` mode (YYYY-MM-DD). Leave empty (default) to let `tool_tests.py` track its own checkpoint file so each run only covers tools installed since the previous run; set explicitly only to force a one-off run against a specific date.

### Control flow variables ###
The following variables can be set to either `yes` or `no` to indicate if the
given part of the role should be executed:

 - `galaxy_tools_install_tools`: (default: `yes`) whether or not to run the
   tools installation script
 - `galaxy_tools_install_state`: (default: `present`) set to `absent` to remove the
   install timers, units and scripts from the host, e.g. when tools are installed
   from CI instead
 - `galaxy_tools_create_bootstrap_user`: (default: `no`) whether or not to
   create a bootstrap Galaxy admin user
 - `galaxy_tools_delete_bootstrap_user`: (default: `no`) whether or not to
   delete a bootstrap Galaxy admin user
