param([string]$OutputDirectory = '')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run setup.ps1 first.' }
if (!$OutputDirectory) { $OutputDirectory = Join-Path $PSScriptRoot ('release\windows-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
& $python -m pip install 'pyinstaller>=6,<7'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed' }
$source = Join-Path $OutputDirectory 'source'
& $python -c 'from build_public_release import build; import sys; build(output=__import__("pathlib").Path(sys.argv[1]))' $source
if ($LASTEXITCODE -ne 0) { throw 'Source audit failed' }
$windows = Join-Path $OutputDirectory 'CloudMotionGUI-Windows'
$work = Join-Path $OutputDirectory 'build-work'
$basePrefix = (& $python -c 'import sys; print(sys.base_prefix)').Trim()
$extraArgs = @()
$condaBin = Join-Path $basePrefix 'Library\bin'
if (Test-Path -LiteralPath (Join-Path $condaBin 'tcl86t.dll')) {
    foreach ($dll in @('tcl86t.dll','tk86t.dll','zlib.dll','zlib-ng2.dll','ffi-7.dll','ffi-8.dll','ffi.dll','libssl-3-x64.dll','libcrypto-3-x64.dll')) {
        $dllPath = Join-Path $condaBin $dll
        if (Test-Path -LiteralPath $dllPath) { $extraArgs += @('--add-binary', ($dllPath + ';.')) }
    }
    $extraArgs += @('--add-data', ((Join-Path $basePrefix 'Library\lib\tcl8.6') + ';_tcl_data'))
    $extraArgs += @('--add-data', ((Join-Path $basePrefix 'Library\lib\tk8.6') + ';_tk_data'))
}
& $python -m PyInstaller @extraArgs --noconfirm --clean --onefile --console --name CloudMotionGUI --distpath $windows --workpath $work --specpath $OutputDirectory (Join-Path $source 'desktop_entry.py')
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
foreach ($name in @('config.example.ini','map.json','README.md','ATTRIBUTION.md','docs','demo_routes')) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination $windows -Recurse
}
& (Join-Path $windows 'CloudMotionGUI.exe') --smoke-test
if ($LASTEXITCODE -ne 0) { throw 'GUI executable smoke test failed' }
& (Join-Path $windows 'CloudMotionGUI.exe') --worker --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Worker entry check failed' }
& (Join-Path $windows 'CloudMotionGUI.exe') --cli --help | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'CLI entry check failed' }
Compress-Archive -LiteralPath $windows -DestinationPath ($windows + '.zip')
Copy-Item -LiteralPath (Join-Path $windows 'CloudMotionGUI.exe') -Destination $source
& $python -c 'import sys,json,hashlib,shutil; from pathlib import Path; r=Path(sys.argv[1]); manifest={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(r.rglob("*")) if p.is_file() and p.name!="PUBLIC_MANIFEST.json"}; (r/"PUBLIC_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8"); shutil.make_archive(str(r),"zip",root_dir=r)' $source
if ($LASTEXITCODE -ne 0) { throw 'GitHub archive creation failed' }

Write-Output ('SOURCE: ' + $source + '.zip')
Write-Output ('WINDOWS: ' + $windows + '.zip')
