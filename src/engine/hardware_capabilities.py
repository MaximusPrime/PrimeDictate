from dataclasses import dataclass

from src.engine.stt_vulkan import VulkanSTTEngine


@dataclass(frozen=True)
class BackendCapability:
    backend: str
    available: bool
    device_name: str
    detail: str = ""


def detect_local_backends() -> dict[str, BackendCapability]:
    capabilities = {
        "cpu": _detect_cpu(),
        "cuda": detect_cuda_backend(),
        "vulkan": _detect_vulkan(),
    }
    return capabilities


def recommended_local_backend(capabilities=None) -> str:
    capabilities = capabilities or detect_local_backends()
    for backend in ("cuda", "vulkan", "cpu"):
        capability = capabilities.get(backend)
        if capability and capability.available:
            return backend
    return "cpu"


def _detect_cpu() -> BackendCapability:
    try:
        import ctranslate2
        compute_types = sorted(ctranslate2.get_supported_compute_types("cpu"))
        detail = ", ".join(compute_types)
        return BackendCapability("cpu", bool(compute_types), "CPU", detail)
    except Exception as error:
        return BackendCapability("cpu", False, "CPU", type(error).__name__)


def preferred_cuda_compute_types(supported_types) -> tuple[str, ...]:
    supported = set(supported_types or ())
    return tuple(
        compute_type
        for compute_type in ("float16", "int8_float16", "int8", "float32")
        if compute_type in supported
    )


def detect_cuda_backend() -> BackendCapability:
    try:
        import ctranslate2
        count = ctranslate2.get_cuda_device_count()
        if count <= 0:
            return BackendCapability("cuda", False, "NVIDIA CUDA", "no_device")
        compute_types = preferred_cuda_compute_types(
            ctranslate2.get_supported_compute_types("cuda", 0)
        )
        if not compute_types:
            return BackendCapability("cuda", False, "NVIDIA CUDA", "unsupported_compute_type")
        return BackendCapability("cuda", True, "NVIDIA CUDA GPU 0", ", ".join(compute_types))
    except Exception as error:
        return BackendCapability("cuda", False, "NVIDIA CUDA", type(error).__name__)


def _detect_vulkan() -> BackendCapability:
    available, message = VulkanSTTEngine.runtime_status()
    device_name = message.split("•", 1)[1].strip() if available and "•" in message else "Vulkan GPU"
    return BackendCapability("vulkan", available, device_name, message)
