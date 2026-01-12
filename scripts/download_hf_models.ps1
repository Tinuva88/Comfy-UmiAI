$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$targetRoot = Join-Path $root 'hf_downloads'

$items = @(
    @{ Url = 'https://huggingface.co/1038lab/RMBG-2.0/resolve/main/config.json'; Path = 'models/RMBG/RMBG-2.0/config.json' },
    @{ Url = 'https://huggingface.co/1038lab/RMBG-2.0/resolve/main/model.safetensors'; Path = 'models/RMBG/RMBG-2.0/model.safetensors' },
    @{ Url = 'https://huggingface.co/1038lab/RMBG-2.0/resolve/main/birefnet.py'; Path = 'models/RMBG/RMBG-2.0/birefnet.py' },
    @{ Url = 'https://huggingface.co/1038lab/RMBG-2.0/resolve/main/BiRefNet_config.py'; Path = 'models/RMBG/RMBG-2.0/BiRefNet_config.py' },
    @{ Url = 'https://huggingface.co/1038lab/inspyrenet/resolve/main/inspyrenet.safetensors'; Path = 'models/RMBG/INSPYRENET/inspyrenet.safetensors' },
    @{ Url = 'https://huggingface.co/1038lab/BEN/resolve/main/model.py'; Path = 'models/RMBG/BEN/model.py' },
    @{ Url = 'https://huggingface.co/1038lab/BEN/resolve/main/BEN_Base.pth'; Path = 'models/RMBG/BEN/BEN_Base.pth' },
    @{ Url = 'https://huggingface.co/1038lab/BEN2/resolve/main/BEN2.py'; Path = 'models/RMBG/BEN2/BEN2.py' },
    @{ Url = 'https://huggingface.co/1038lab/BEN2/resolve/main/BEN2_Base.pth'; Path = 'models/RMBG/BEN2/BEN2_Base.pth' },
    @{ Url = 'https://huggingface.co/bartowski/JoyCaption-Alpha-Two-Llama3-GGUF/resolve/main/JoyCaption-Alpha-Two-Llama3-Q4_K_M.gguf'; Path = 'models/llm/JoyCaption-Alpha-Two-Llama3-Q4_K_M.gguf' },
    @{ Url = 'https://huggingface.co/bartowski/JoyCaption-Alpha-Two-Llama3-GGUF/resolve/main/JoyCaption-Alpha-Two-Llama3-mmproj-f16.gguf'; Path = 'models/llm/JoyCaption-Alpha-Two-Llama3-mmproj-f16.gguf' },
    @{ Url = 'https://huggingface.co/cjpais/llava-1.5-7b-gguf/resolve/main/llava-v1.5-7b-Q4_K.gguf'; Path = 'models/llm/llava-v1.5-7b-Q4_K.gguf' },
    @{ Url = 'https://huggingface.co/cjpais/llava-1.5-7b-gguf/resolve/main/llava-v1.5-7b-mmproj-Q4_0.gguf'; Path = 'models/llm/llava-v1.5-7b-mmproj-Q4_0.gguf' },
    @{ Url = 'https://huggingface.co/bartowski/Qwen2.5-Coder-1.5B-Instruct-abliterated-GGUF/resolve/main/Qwen2.5-Coder-1.5B-Instruct-abliterated-Q4_K_M.gguf'; Path = 'models/llm/Qwen2.5-Coder-1.5B-Instruct-abliterated-Q4_K_M.gguf' },
    @{ Url = 'https://huggingface.co/bartowski/dolphin-2.9.4-llama3.1-8b-GGUF/resolve/main/dolphin-2.9.4-llama3.1-8b-Q4_K_M.gguf'; Path = 'models/llm/dolphin-2.9.4-llama3.1-8b-Q4_K_M.gguf' },
    @{ Url = 'https://huggingface.co/mradermacher/Wingless_Imp_8B-GGUF/resolve/main/Wingless_Imp_8B.Q4_K_M.gguf'; Path = 'models/llm/Wingless_Imp_8B.Q4_K_M.gguf' }
)

foreach ($item in $items) {
    $outPath = Join-Path $targetRoot $item.Path
    $outDir = Split-Path -Parent $outPath
    if (-not (Test-Path $outDir)) {
        New-Item -ItemType Directory -Path $outDir | Out-Null
    }
    Write-Host "Downloading $($item.Url) -> $outPath"
    Invoke-WebRequest -Uri $item.Url -OutFile $outPath
}

Write-Host "Done. Files saved under: $targetRoot"
