import logging
import time


def execute_with_ledger(transport, command, source, decode, *, replay=False, read_only=False):
    """Execute one debugger/Lua boundary call and log exactly one outcome row."""
    started=time.monotonic()
    try:
        raw=transport.execute(source)
        duration=getattr(transport,'last_duration',0.0)
        if type(duration) not in (int,float) or duration<=0:duration=time.monotonic()-started
        result=decode(raw)
    except Exception as error:
        duration=getattr(transport,'last_duration',0.0)
        if type(duration) not in (int,float) or duration<=0:duration=time.monotonic()-started
        # A decode failure after a successful transport means the Lua action
        # executed but the host could not interpret the result.  For
        # non-idempotent operations this is an outcome_unknown path: taint the
        # transport so the host does not silently retry.
        if not getattr(error, '_mgt_transport_failure', False) and not read_only:
            transport.tainted = True
        logging.info(
            'LuaBoundary command=%s duration=%.3fs outcome=%s crossed_transport=yes replay=%s readOnly=%s',
            command,duration,getattr(error,'code',type(error).__name__),bool(replay),bool(read_only),
        )
        raise
    logging.info(
        'LuaBoundary command=%s duration=%.3fs outcome=ok crossed_transport=yes replay=%s readOnly=%s',
        command,duration,bool(replay),bool(read_only),
    )
    return result
