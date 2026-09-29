import json
import time
import logging
import inspect

log = logging.getLogger(__name__)

def safe_repr(obj, maxlen=800):
    try:
        r = repr(obj)
    except Exception:
        r = f"<unrepr {type(obj).__name__}>"
    return r if len(r) <= maxlen else r[:maxlen] + "..."

def summarize_obj(o, attrs=None, limit=50):
    summary = {}
    if attrs is None:
        names = [n for n in dir(o) if not n.startswith("_")]
    else:
        names = [n for n in attrs if hasattr(o, n)]
    for n in names[:limit]:
        try:
            v = getattr(o, n)
            summary[n] = {"type": type(v).__name__, "repr": safe_repr(v)}
        except Exception as e:
            summary[n] = {"type": "ERROR", "repr": safe_repr(e)}
    
    return summary

try:
    job = getattr(entity, "job", None) or getattr(entity, "job_id", None)
    jobid = None
    if job is not None:
        jobid = getattr(job, "id", None) or str(job)
    if not jobid:
        jobid = str(int(time.time()))
    fn = f"/tmp/tpv_entity_{jobid}.json"
    out = {
        "dump_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "job_id": jobid,
        "entity_type": type(entity).__name__,
        "entity_dir": [n for n in dir(entity) if not n.startswith("_")][:200],
        "destinations": getattr(mapper, "destinations", None),
        "entity_summary": summarize_obj(entity, limit=200),
    }
    
    import json

    # Create a copy of the local variables to iterate over safely
    local_vars_copy = locals().copy()
    summarized_vars = {}

    for name, value in local_vars_copy.items():
        # The 'summarize_obj' function seems to be for this purpose
        try:
            summarized_vars[name] = summarize_obj(value)
        except Exception as e:
            # Fallback to a simple string representation if summarize_obj fails
            try:
                summarized_vars[name] = repr(value)
            except Exception:
                summarized_vars[name] = f"Error summarizing object: {e}"


    # Create a copy of the keys to prevent "dictionary changed size during iteration" error
    local_keys = list(locals().keys())

    # locals() gives us all local variables available in this context
    for key in local_keys:
        if key in ['__builtins__', 'local_keys', 'key']:  # Exclude noisy builtins and our own temp vars
            continue
        try:
            value = locals()[key]
            # Use repr to get a string representation of the object
            out[key] = safe_repr(value)
        except Exception as e:
            out[key] = f"Error getting repr: {e}"   
    # add focused nested summaries if present
    for nested in ("user", "tool", "job", "tpv_tags", "tags", "destination_params", "context"):
        if hasattr(entity, nested):
            try:
                out[nested] = {
                    "type": type(getattr(entity, nested)).__name__,
                    "summary": summarize_obj(getattr(entity, nested), limit=200),
                }
            except Exception as e:
                out[nested] = {"error": safe_repr(e)}
    with open(fn, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
        json.dump(summarized_vars, fh, indent=2, default=str)
    log.debug(f"Wrote TPV entity dump to {fn}")
except Exception:
    log.exception("TPV debug dump failed")