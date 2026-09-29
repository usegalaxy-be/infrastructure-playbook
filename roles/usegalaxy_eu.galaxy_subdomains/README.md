# ansible-galaxy-subdomains

Sets up the fancy subsite CSS/welcome pages and tool sections on a per-subdomain basis like EU does

## Role Variables

Variable | Default | Meaning
-- | -- | --
`galaxy_subsite_base_domain` | `usegalaxy.org`
`galaxy_subsite_dir` | `/srv/subsite`
`galaxy_subsite_base_css` | `#masthead { background-color: #003399;}` |
`galaxy_subsites` | See below | Subdomain listing and configuration.
`galaxy_subsite_nginx_routes` | complex | Some default nginx routes you can plop in your nginx routes.


## Example Playbook

```
- name: usegalaxy.aq
  hosts: galaxy
  become: true
  vars:
    galaxy_subsite_base_domain: usegalaxy.aq
    galaxy_subsites:
      - name: virus # Accessible at virus.usegalaxy.aq
        brand: Viruses
        iframe: "https://galaxyproject.aq/viruses.html"
        tool_sections: # The tool section ids to display, generic tools will always be displayed and the list of these can be found in `defaults/main.yml`
          - "hicexplorer"
          - "graph_display_data"
          - "peak_calling"
          - "assembly"
          - "annotation"
          - "genome_diversity"
          - "multiple_alignments"
        custom_css: |
            #masthead {
                background: linear-gradient(to bottom,#e2453c 0,#e2453c 16%,#e07e39 16%,#e07e39 32%,#e5d667 32%,#e5d667 48%,#51b95b 48%,#51b95b 66%,#1e72b7 66%,#1e72b7 86%,#6f5ba7 86%) no-repeat;
            }
            #masthead .navbar-brand {
              background: #3337;
              height: 100%;
              padding: 0.5em;
              left: 0px;
            }
            #masthead .navbar-nav > li .nav-link {
                color: white;
            }
            #masthead .navbar-nav > li {
                background: #3337;
            }
            #masthead .navbar-nav > li.active {
                background: #333e;
            }
  roles:
    - galaxyproject.galaxy
    - usegalaxy_eu.galaxy_subdomains
    - galaxyproject.nginx
```

## Role Dependencies

- galaxyproject.galaxy (depends on Galaxy variables like `galaxy_server_dir`)
- galaxyproject.nginx (supplies routes for nginx)

Many variables from that role are set. It is assumed you will use that in your playbook as well.

## License

GPLv3

## Authors

- [Helena Rasche](@hexylena)
- [Björn Grüning](@bgruening)
- [Gianmauro Cuccuru](@gmauro)
- [Simon Gladman](@slugger70)
