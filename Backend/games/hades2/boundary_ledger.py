import logging
import time


def execute_with_ledger(transport, command, source, decode, *, replay=False, read_only=False):
    """Execute one debugger/Lua boundary call and log exactly one outcome row."""
    started=time.monotonic()
    crossed=False
    try:
        raw=transport.execute(source)
        crossed=True
        duration=getattr(transport,'last_duration',0.0)
        if type(duration) not in (int,float) or duration<=0:duration=time.monotonic()-started
        result=decode(raw)
    except Exception as error:
        duration=getattr(transport,'last_duration',0.0)
        if type(duration) not in (int,float) or duration<=0:duration=time.monotonic()-started
        if crossed and not read_only:
            # The Lua boundary was crossed and returned a result, but the host
            # could not decode it: for non-read-only commands the action may
            # already have executed, so this is an outcome-unknown path. Taint
            # the transport so the host cannot silently retry it. Failures from
            # transport.execute itself (crossed is False) keep their own
            # semantics: the transport already taints itself on
            # outcome_unknown, and lua_error means the chunk did not complete.
            transport.tainted=True
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
