import argparse
# import sys
import json
import requests
import yaml
# from bioblend.galaxy import GalaxyInstance

def check_singularity_compatibility(tool_test_output, tpv_config_output):
    with open(tool_test_output, "r") as f:
        tool_tests = json.load(f)
        
    tpv_singularity_tools = {}
    for tool_test in tool_tests["tests"]:
        if tool_test["data"]["status"] == "failure":
            tpv_singularity_tools[tool_test["id"]] = {"inherits": "_legacy"}
                 
    with open('tpv_config_output', 'w', encoding='utf8') as outfile:
        yaml.dump(tpv_singularity_tools, outfile, default_flow_style=False, allow_unicode=True)
    

# python ephemeris_output_parse.py -j tool_test_output.json -o tpv_singularity_tools.yaml

def main():

    parser = argparse.ArgumentParser(description='Parses ephemeris tool test output json and checks singularity compatibility')
    parser.add_argument("-j", "--tool_test_output", default=None, help="ephemeris tool test output json")
    parser.add_argument("-o", "--tpv_config_output", default=None, help="tpv configuration output in yaml")
    args = parser.parse_args()
    check_singularity_compatibility(args.tool_test_output, args.tpv_config_output)

if __name__ == '__main__':
    main()
