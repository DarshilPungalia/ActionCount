# friday_setup.ps1
# Run from the ActionCount repo root:
#   cd C:\Users\LENOVO\Desktop\Git_repos\ActionCount
#   .\friday_setup.ps1
#
# What this script does:
#   1. Builds CrispASR (STT runtime) with CUDA support via CMake + MSVC
#   2. Downloads Qwen3-ASR Q4_K GGUF (~1.33 GB)
#   3. Verifies CrispASR + Qwen3-ASR end-to-end
#   4. Installs Rust if not present, builds voxtral-mini-realtime-rs (TTS runtime)
#   5. Downloads Voxtral Q4_0 GGUF (~2.67 GB)
#   6. Verifies Voxtral TTS
#   7. Appends required env vars to .env
#   8. Installs Python dependencies
#   9. GATE CHECK: exits with code 1 if any binary is missing
#
# Prerequisites (install before running):
#   - Visual Studio 2022 with "Desktop development with C++" workload
#   - CUDA Toolkit 12.x
#   - CMake >= 3.26  (winget install Kitware.CMake)
#   - Git
#   - Python 3.10+

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO_ROOT      = $PSScriptRoot
$USERPROFILE_DIR = $env:USERPROFILE

$CRISPASR_DIR      = "$USERPROFILE_DIR\crispasr"
# CrispASR outputs to build\bin\Release\crispasr.exe (target name is crispasr-cli, exe name is crispasr)
$CRISPASR_BIN      = "$CRISPASR_DIR\build\bin\Release\crispasr.exe"
$QWEN3_MODEL_DIR   = "$REPO_ROOT\models\qwen3-asr"
$QWEN3_MODEL       = "$QWEN3_MODEL_DIR\qwen3-asr-1.7b-q4_k.gguf"

$VOXTRAL_DIR       = "$USERPROFILE_DIR\voxtral-rs"
$VOXTRAL_BIN       = "$VOXTRAL_DIR\target\release\voxtral.exe"
$VOXTRAL_MODEL_DIR = "$REPO_ROOT\models\voxtral"
$VOXTRAL_MODEL     = "$VOXTRAL_MODEL_DIR\voxtral-tts-q4.gguf"

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
}
function Write-OK([string]$msg)   { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  WARN $msg" -ForegroundColor Yellow }
function Write-Fail([string]$msg) { Write-Host "  FAIL $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------------------
# PREREQ 1 -- Build CrispASR
# ---------------------------------------------------------------------------
Write-Step "PREREQ 1 -- Build CrispASR (STT Runtime)"

if (Test-Path $CRISPASR_BIN) {
    Write-OK "CrispASR binary already exists: $CRISPASR_BIN -- skipping build."
}
else {
    Write-Host "  Cloning CrispASR into $CRISPASR_DIR ..."
    if (-not (Test-Path $CRISPASR_DIR)) {
        git clone https://github.com/CrispStrobe/CrispASR $CRISPASR_DIR
    }
    else {
        Write-Warn "Directory already exists -- skipping clone."
    }

    Push-Location $CRISPASR_DIR
    try {
        Write-Host "  Configuring CMake with CUDA support ..."
        cmake -B build `
              -DCMAKE_BUILD_TYPE=Release `
              -DGGML_CUDA=ON `
              -G "Visual Studio 17 2022" `
              -A x64

        Write-Host "  Building (Release) -- this may take 15-30 minutes (CUDA kernel compilation) ..."
        cmake --build build --config Release --target crispasr-cli

        # CrispASR outputs to build\bin\Release\crispasr.exe
        $alt  = "$CRISPASR_DIR\build\bin\Release\crispasr.exe"
        $alt2 = "$CRISPASR_DIR\build\Release\whisper-cli.exe"
        if (-not (Test-Path $CRISPASR_BIN)) {
            if (Test-Path $alt) {
                Copy-Item $alt $CRISPASR_BIN -Force
            }
            else {
                Write-Fail "Build finished but crispasr.exe not found. Check build output above."
            }
        }
    }
    finally {
        Pop-Location
    }
    Write-OK "CrispASR built: $CRISPASR_BIN"
}

# ---------------------------------------------------------------------------
# PREREQ 2 -- Download Qwen3-ASR Q4_K GGUF
# ---------------------------------------------------------------------------
Write-Step "PREREQ 2 -- Download Qwen3-ASR Q4_K GGUF (~1.33 GB)"

if (Test-Path $QWEN3_MODEL) {
    Write-OK "Model already downloaded: $QWEN3_MODEL -- skipping."
}
else {
    New-Item -ItemType Directory -Force -Path $QWEN3_MODEL_DIR | Out-Null
    Write-Host "  Downloading via huggingface_hub ..."
    $pyScript = @"
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    repo_id='cstr/qwen3-asr-1.7b-GGUF',
    filename='qwen3-asr-1.7b-q4_k.gguf',
    local_dir=r'$QWEN3_MODEL_DIR',
)
print('Downloaded to: ' + path)
"@
    python -c $pyScript
    if (-not (Test-Path $QWEN3_MODEL)) {
        Write-Fail "Download failed -- file not found at $QWEN3_MODEL"
    }
    Write-OK "Model downloaded: $QWEN3_MODEL"
}

# ---------------------------------------------------------------------------
# PREREQ 3 -- Verify CrispASR + Qwen3-ASR
# ---------------------------------------------------------------------------
Write-Step "PREREQ 3 -- Verify CrispASR end-to-end"

$TEST_WAV = "$CRISPASR_DIR\samples\jfk.wav"
if (-not (Test-Path $TEST_WAV)) {
    Write-Warn "JFK sample not found -- downloading fallback ..."
    $TEST_WAV = "$env:TEMP\friday_test_jfk.wav"
    Invoke-WebRequest `
        -Uri "https://github.com/ggerganov/whisper.cpp/raw/master/samples/jfk.wav" `
        -OutFile $TEST_WAV
}

Write-Host "  Running transcription test ..."
$result = cmd.exe /c "`"$CRISPASR_BIN`" --backend qwen3 -m `"$QWEN3_MODEL`" -f `"$TEST_WAV`" -l en --no-timestamps 2>&1"
Write-Host "  Output: $result"

if ($result -match "ask not what") {
    Write-OK "CrispASR + Qwen3-ASR VERIFIED."
}
else {
    Write-Warn "Transcript mismatch -- review output above manually. Continuing anyway."
}

# ---------------------------------------------------------------------------
# PREREQ 4 -- Install Rust + Build voxtral-mini-realtime-rs
# ---------------------------------------------------------------------------
Write-Step "PREREQ 4 -- Build voxtral-mini-realtime-rs (TTS Runtime)"

if (Test-Path $VOXTRAL_BIN) {
    Write-OK "Voxtral binary already exists: $VOXTRAL_BIN -- skipping build."
}
else {
    $rustup = Get-Command rustup -ErrorAction SilentlyContinue
    if (-not $rustup) {
        Write-Host "  Rust not found -- installing via winget ..."
        winget install Rustlang.Rustup --accept-source-agreements --accept-package-agreements
        # Reload PATH so cargo is available in this session
        $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::Machine)
        $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", [System.EnvironmentVariableTarget]::User)
        $env:PATH    = "$machinePath;$userPath"
        Write-Host "  Rust installed. If 'cargo' is not recognized below, close and reopen"
        Write-Host "  this terminal, then re-run the script from step 4 onwards."
    }
    else {
        Write-OK "Rust already installed."
    }

    if (-not (Test-Path $VOXTRAL_DIR)) {
        Write-Host "  Cloning voxtral-mini-realtime-rs ..."
        git clone https://github.com/TrevorS/voxtral-mini-realtime-rs $VOXTRAL_DIR
    }
    else {
        Write-Warn "voxtral-rs directory already exists -- skipping clone."
    }

    Push-Location $VOXTRAL_DIR
    try {
        Write-Host "  Building Voxtral with WGPU (may take 10-20 min on first build) ..."
        cargo build --release --features "wgpu,cli,hub"
    }
    finally {
        Pop-Location
    }

    if (-not (Test-Path $VOXTRAL_BIN)) {
        Write-Fail "Build finished but binary not found at $VOXTRAL_BIN"
    }
    Write-OK "Voxtral built: $VOXTRAL_BIN"
}

# ---------------------------------------------------------------------------
# PREREQ 5 -- Download Voxtral Q4_0 GGUF
# ---------------------------------------------------------------------------
Write-Step "PREREQ 5 -- Download Voxtral Q4_0 GGUF (~2.67 GB)"

if (Test-Path $VOXTRAL_MODEL) {
    Write-OK "Voxtral model already downloaded: $VOXTRAL_MODEL -- skipping."
}
else {
    New-Item -ItemType Directory -Force -Path $VOXTRAL_MODEL_DIR | Out-Null
    Write-Host "  Downloading via huggingface_hub ..."
    $pyScript2 = @"
$pyScript2 = @"
from huggingface_hub import snapshot_download
path = snapshot_download(
    repo_id='TrevorJS/voxtral-tts-q4-gguf',
    allow_patterns=['*.gguf', '*.json', 'voice_embedding/*'],
    local_dir=r'$VOXTRAL_MODEL_DIR',
)
print('Downloaded to: ' + path)
"@
    python -c $pyScript2
    if (-not (Test-Path $VOXTRAL_MODEL)) {
        Write-Fail "Download failed -- file not found at $VOXTRAL_MODEL"
    }
    Write-OK "Voxtral model downloaded: $VOXTRAL_MODEL"
}

# ---------------------------------------------------------------------------
# PREREQ 6 -- Verify Voxtral TTS
# ---------------------------------------------------------------------------
Write-Step "PREREQ 6 -- Verify Voxtral TTS"

Write-Host "  Checking available voices ..."
cmd.exe /c "`"$VOXTRAL_BIN`" speak --help 2>&1"

$TTS_TEST_WAV = "$env:TEMP\friday_tts_verify.wav"
Write-Host "  Synthesizing test phrase ..."
cmd.exe /c "`"$VOXTRAL_BIN`" speak --text `"Friday TTS verification test.`" --voice casual_female --gguf `"$VOXTRAL_MODEL`" --tokenizer `"$VOXTRAL_MODEL_DIR\tekken.json`" --voices-dir `"$VOXTRAL_MODEL_DIR\voice_embedding`" --euler-steps 4 --output `"$TTS_TEST_WAV`" 2>&1"

if (Test-Path $TTS_TEST_WAV) {
    $size = (Get-Item $TTS_TEST_WAV).Length
    if ($size -gt 1000) {
        Write-OK "Voxtral produced WAV ($size bytes) -- playing back ..."
        (New-Object Media.SoundPlayer $TTS_TEST_WAV).PlaySync()
        Write-OK "Voxtral TTS VERIFIED."
    }
    else {
        Write-Fail "WAV too small ($size bytes) -- synthesis may have failed."
    }
}
else {
    Write-Fail "Output WAV not created at $TTS_TEST_WAV"
}

# ---------------------------------------------------------------------------
# PREREQ 7 -- Append env vars to .env
# ---------------------------------------------------------------------------
Write-Step "PREREQ 7 -- Update .env with CrispASR + Voxtral paths"

$ENV_FILE   = "$REPO_ROOT\.env"
$envContent = Get-Content $ENV_FILE -Raw

if ($envContent -notmatch "CRISPASR_BINARY") {
    $newVars = @"

# -- STT - Qwen3-ASR via CrispASR (local, no API key needed) --
CRISPASR_BINARY=$CRISPASR_BIN
QWEN3_ASR_MODEL=$QWEN3_MODEL
QWEN3_ASR_LANGUAGE=en

# -- TTS - Voxtral via voxtral-mini-realtime-rs (local sounddevice playback) --
VOXTRAL_BINARY=$VOXTRAL_BIN
VOXTRAL_MODEL=$VOXTRAL_MODEL
VOXTRAL_VOICE=casual_female
VOXTRAL_EULER_STEPS=4
"@
    Add-Content -Path $ENV_FILE -Value $newVars
    Write-OK ".env updated with CrispASR + Voxtral paths."
}
else {
    Write-Warn "CRISPASR_BINARY already in .env -- skipping append. Review manually."
}

# ---------------------------------------------------------------------------
# PREREQ 8 -- Python Dependencies
# ---------------------------------------------------------------------------
Write-Step "PREREQ 8 -- Install Python dependencies"

pip install "sounddevice>=0.4.6" "soundfile>=0.12.1" "scipy>=1.11.0" huggingface_hub
python -c "import sounddevice, soundfile, scipy; print('All STT/TTS Python deps OK')"

# ---------------------------------------------------------------------------
# GATE CHECK
# ---------------------------------------------------------------------------
Write-Step "GATE CHECK -- Confirming all binaries and models exist"

$gate_pass = $true

if (Test-Path $CRISPASR_BIN) {
    Write-OK "CrispASR binary : $CRISPASR_BIN"
}
else {
    Write-Host "  FAIL CrispASR binary MISSING: $CRISPASR_BIN" -ForegroundColor Red
    $gate_pass = $false
}

if (Test-Path $VOXTRAL_BIN) {
    Write-OK "Voxtral binary  : $VOXTRAL_BIN"
}
else {
    Write-Host "  FAIL Voxtral binary MISSING: $VOXTRAL_BIN" -ForegroundColor Red
    $gate_pass = $false
}

if (Test-Path $QWEN3_MODEL) {
    Write-OK "Qwen3-ASR model : $QWEN3_MODEL"
}
else {
    Write-Host "  FAIL Qwen3-ASR model MISSING: $QWEN3_MODEL" -ForegroundColor Red
    $gate_pass = $false
}

if (Test-Path $VOXTRAL_MODEL) {
    Write-OK "Voxtral model   : $VOXTRAL_MODEL"
}
else {
    Write-Host "  FAIL Voxtral model MISSING: $VOXTRAL_MODEL" -ForegroundColor Red
    $gate_pass = $false
}

Write-Host ""
if ($gate_pass) {
    Write-Host "===============================================" -ForegroundColor Green
    Write-Host "  ALL PREREQUISITES COMPLETE" -ForegroundColor Green
    Write-Host "  stt.py and tts.py are ready to run." -ForegroundColor Green
    Write-Host "===============================================" -ForegroundColor Green
}
else {
    Write-Host "===============================================" -ForegroundColor Red
    Write-Host "  GATE FAILED -- one or more binaries missing." -ForegroundColor Red
    Write-Host "  Review errors above before starting backend." -ForegroundColor Red
    Write-Host "===============================================" -ForegroundColor Red
    exit 1
}
