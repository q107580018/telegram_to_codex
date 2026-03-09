class PreviewDriver:
    async def start(self) -> None:
        raise NotImplementedError

    async def update(self, text: str) -> None:
        raise NotImplementedError

    async def finalize(self) -> None:
        raise NotImplementedError

    async def fail(self, error_text: str) -> None:
        raise NotImplementedError


class NullPreviewDriver(PreviewDriver):
    async def start(self) -> None:
        return None

    async def update(self, text: str) -> None:
        return None

    async def finalize(self) -> None:
        return None

    async def fail(self, error_text: str) -> None:
        return None
