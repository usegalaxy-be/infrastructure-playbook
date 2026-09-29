import sys
import os
import subprocess
#import shutil
from bioblend.galaxy import GalaxyInstance
from bioblend.galaxy.histories import HistoryClient
from bioblend.galaxy.tools import ToolClient
from bioblend.galaxy.toolshed import ToolShedClient
from bioblend.galaxy.workflows import WorkflowClient
from bioblend.galaxy.tool_data import ToolDataClient
#from bioblend.galaxy.datasets import DatasetClient



instance_name=sys.argv[1]

URLS={}
API_KEYS={}

# Seed the secret yourself first if not already set, this script never writes to Vault:
#   vault kv put vsc/prod/usegalaxy-be/misc/tool_list_api_keys \
#     usegalaxy_be=<key> usegalaxy_eu=<key> usegalaxy_au=<key>
VAULT_TOOL_LIST_PATH = 'vsc/prod/usegalaxy-be/misc/tool_list_api_keys'


def _vault_field(path, field):
    """Fetch one field from Vault via the CLI. Returns '' on any failure (no vault CLI, no token, missing key)."""
    try:
        out = subprocess.run(
            ['vault', 'kv', 'get', '-field', field, path],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else ''
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ''


API_KEY_USEGALAXY_BE = os.environ.get('API_KEY_USEGALAXY_BE') or _vault_field(VAULT_TOOL_LIST_PATH, 'usegalaxy_be')
API_KEY_USEGALAXY_EU = os.environ.get('API_KEY_USEGALAXY_EU') or _vault_field(VAULT_TOOL_LIST_PATH, 'usegalaxy_eu')
API_KEY_USEGALAXY_AU = os.environ.get('API_KEY_USEGALAXY_AU') or _vault_field(VAULT_TOOL_LIST_PATH, 'usegalaxy_au')

#Vsc prod
URLS['usegalaxy_be']= 'https://usegalaxy.be'
API_KEYS['usegalaxy_be']= API_KEY_USEGALAXY_BE

#usegalaxy_eu
URLS['usegalaxy_eu']= 'https://usegalaxy.eu'
API_KEYS['usegalaxy_eu']= API_KEY_USEGALAXY_EU

#usegalaxy_au
URLS['usegalaxy_au']= 'https://usegalaxy.org.au'
API_KEYS['usegalaxy_au']= API_KEY_USEGALAXY_AU


GALAXY_URL = URLS[instance_name]
API_KEY= API_KEYS[instance_name]


installed_tools=[]

def main():
        galaxyInstance = GalaxyInstance(url = GALAXY_URL, key=API_KEY)
        toolClient = ToolClient(galaxyInstance)
	toolShedClient= ToolShedClient(galaxyInstance)
	toolDataClient= ToolDataClient(galaxyInstance)
        histories = HistoryClient(galaxyInstance)
	workflowsClient= WorkflowClient(galaxyInstance)
	#print(toolClient.get_tool_panel())
	tools_list= toolShedClient.get_repositories()
	for entry in tools_list:
		#{u'tool_shed_status': {u'latest_installable_revision': u'True', u'revision_update': u'False', u'revision_upgrade': u'False', u'repository_deprecated': u'False'}, u'status': u'Installed', u'name': u'ageseq', u'deleted': False, u'ctx_rev': u'7', u'error_message': u'', u'installed_changeset_revision': u'449c8cf8fa3f', u'tool_shed': u'toolshed.g2.bx.psu.edu', u'dist_to_shed': False, u'url': u'/api/tool_shed_repositories/964b37715ec9bd22', u'id': u'964b37715ec9bd22', u'owner': u'lxue', u'uninstalled': False, u'changeset_revision': u'449c8cf8fa3f', u'includes_datatypes': False}
		if entry['status'] == 'Installed' and entry['uninstalled'] == False:
			#print entry['name'] + '\t' + entry['tool_shed'] + '\t' + entry['installed_changeset_revision']
			installed_tools.append(entry['name'])
        tool_panel_entries= toolClient.get_tool_panel()
	for entry in tool_panel_entries:
		section_id=entry['id']
		if 'elems' in entry.keys():
			#print 'here'
			for tool in entry['elems']:
				if 'tool_shed_repository' in tool.keys():
					print section_id + '\t' + tool['tool_shed_repository']['name'] + '\t' + tool['tool_shed_repository']['tool_shed'] + '\t' + tool['tool_shed_repository']['changeset_revision'] + '\t' + tool['tool_shed_repository']['owner'] 


if __name__ == '__main__':
    main()
