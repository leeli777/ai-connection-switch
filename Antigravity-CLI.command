#!/bin/zsh
export HTTP_PROXY=http://127.0.0.1:1087
export HTTPS_PROXY=$HTTP_PROXY ALL_PROXY=$HTTP_PROXY
export http_proxy=$HTTP_PROXY https_proxy=$HTTP_PROXY all_proxy=$HTTP_PROXY grpc_proxy=$HTTP_PROXY
export NO_PROXY=localhost,127.0.0.1,::1
export no_proxy=$NO_PROXY no_grpc_proxy=$NO_PROXY
for cli in "${commands[agy]:-}" "$HOME/.local/bin/agy" "/Applications/Gemini.app/Contents/Helpers/agy"; do
    if [[ -f "$cli" && -x "$cli" ]]; then
        exec "$cli" "$@"
    fi
done
print -u2 '找不到 agy，请先安装 Antigravity CLI。'
exit 1
