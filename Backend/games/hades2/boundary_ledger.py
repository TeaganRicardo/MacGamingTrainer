import logging
import time

from core.adapter import AdapterError


def execute_with_ledger(transport, command, source, decode, *, replay=False, read_only=False, expression_timeout_seconds=None):
    """Execute one debugger/Lua boundary call and log exactly one outcome row."""
    started=time.monotonic()
    crossed=False
    try:
        if expression_timeout_seconds is None:
            raw=transport.execute(source)
        else:
            raw=transport.execute(source, expression_timeout_seconds=expression_timeout_seconds)
        crossed=True
        duration=getattr(transport,'last_duration',0.0)
        if type(duration) not in (int,float) or duration<=0:duration=time.monotonic()-started
        result=decode(raw)
    except Exception as error:
        duration=getattr(transport,'last_duration',0.0)
        if type(duration) not in (int,float) or duration<=0:duration=time.monotonic()-started
        if crossed:
            # Lua returned, but the host cannot establish its outcome. Even
            # status may perform resident maintenance before returning.
            transport.tainted=True
        logging.info(
            'LuaBoundary command=%s duration=%.3fs outcome=%s crossed_transport=%s replay=%s readOnly=%s decodeError=%s expression=%.3fs',
            command,duration,'outcome_unknown' if crossed else getattr(error,'code',type(error).__name__),
            'yes' if crossed else 'no',bool(replay),bool(read_only),type(error).__name__ if crossed else 'none',
            getattr(transport,'last_expression_duration',0.0) or 0.0,
        )
        if crossed:
            raise AdapterError('outcome_unknown', '游戏调用结果不明，未自动重试；请检查游戏并重启。') from error
        raise
    logging.info(
        'LuaBoundary command=%s duration=%.3fs outcome=ok crossed_transport=yes replay=%s readOnly=%s expression=%.3fs',
        command,duration,bool(replay),bool(read_only),getattr(transport,'last_expression_duration',0.0) or 0.0,
    )
    return result
