"""Private worker-session files carry JSON values larger than a control frame."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import uuid

SESSION_ENVIRONMENT = 'MGT_JSONL_SESSION_V1'
_PAYLOAD_NAME = re.compile(r'^payload-[0-9a-f]{32}\.json$')


class FramingError(ValueError):
    def __init__(self, message, request_id=None):
        super().__init__(message)
        self.request_id = request_id


def decode_json(raw):
    return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
        ValueError('non-finite JSON value: ' + value)))


class JsonLineFileSession:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.descriptor = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self._open('session.json') as handle:
                configuration = decode_json(handle.read())
            if (not isinstance(configuration, dict) or configuration.get('version') != 1
                    or type(configuration.get('inlineBytes')) is not int
                    or not 4096 <= configuration['inlineBytes'] <= 1024 * 1024
                    or type(configuration.get('hostPID')) is not int or configuration['hostPID'] <= 0):
                raise ValueError('Invalid private JSONL session configuration.')
            self.inline_bytes = configuration['inlineBytes']
            self.host_pid = configuration['hostPID']
        except BaseException:
            self.close()
            raise

    @classmethod
    def from_environment(cls):
        directory = os.environ.get(SESSION_ENVIRONMENT)
        return cls(directory) if directory else None

    def close(self, *, remove_if_orphaned=False):
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
        if remove_if_orphaned and self.host_pid is not None and os.getppid() != self.host_pid:
            shutil.rmtree(self.directory)

    def _open(self, name):
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self.descriptor)
        handle = os.fdopen(descriptor, 'rb')
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            handle.close()
            raise ValueError('Private JSONL payload must be a regular file.')
        return handle

    def decode(self, raw):
        envelope = decode_json(raw)
        if not isinstance(envelope, dict) or envelope.get('type') != 'mgt.file':
            return envelope
        request_id = envelope.get('id')
        request_id = request_id if isinstance(request_id, str) and 0 < len(request_id) <= 128 else None
        name, length = envelope.get('file'), envelope.get('bytes')
        if (set(envelope) != {'id', 'type', 'file', 'bytes'} or request_id is None
                or not isinstance(name, str) or not _PAYLOAD_NAME.fullmatch(name)
                or type(length) is not int or length < self.inline_bytes):
            raise FramingError('Invalid private JSONL payload descriptor.', request_id)
        try:
            with self._open(name) as handle:
                if os.fstat(handle.fileno()).st_size != length:
                    raise ValueError('Private JSONL payload length does not match its descriptor.')
                payload = handle.read()
                if len(payload) != length:
                    raise ValueError('Private JSONL payload changed while reading.')
            value = decode_json(payload)
            if not isinstance(value, dict) or value.get('id') != request_id:
                raise ValueError('Private JSONL payload identity does not match its descriptor.')
            return value
        except (OSError, ValueError, RecursionError) as error:
            raise FramingError(str(error), request_id) from error
        finally:
            try:
                os.unlink(name, dir_fd=self.descriptor)
            except FileNotFoundError:
                pass

    def encode(self, encoded, request_id):
        payload = encoded.encode('utf-8')
        if len(payload) + 1 <= self.inline_bytes:
            return encoded
        name = 'payload-' + uuid.uuid4().hex + '.json'
        temporary = '.' + name
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=self.descriptor)
        try:
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(payload)
            os.replace(temporary, name, src_dir_fd=self.descriptor, dst_dir_fd=self.descriptor)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.descriptor)
            except FileNotFoundError:
                pass
        return json.dumps({'id': request_id, 'type': 'mgt.file', 'file': name, 'bytes': len(payload)},
                          separators=(',', ':'))
