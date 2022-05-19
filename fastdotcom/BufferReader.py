
from io import BytesIO


class BufferReader(BytesIO):
    def __init__(self, buf=b'',
                 callback=None,
                 cb_args=(),
                 cb_kwargs={}):
        self._callback = callback
        self._cb_args = cb_args
        self._cb_kwargs = cb_kwargs
        self._progress = 0
        self._len = len(buf)
        BytesIO.__init__(self, buf)

    def __len__(self):
        return self._len

    def read(self, n=-1):
        n = 1024
        chunk = BytesIO.read(self, n)
        self._progress += int(len(chunk))
        self._cb_kwargs.update({
            'size': self._len,
            'progress': self._progress,
            'chunk_len': len(chunk)
        })
        if self._callback:
            try:
                self._callback(*self._cb_args, **self._cb_kwargs)
            except:  # catches exception from the callback
                pass
        return chunk
