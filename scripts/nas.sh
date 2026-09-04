#!/usr/bin/env bash
#
# 真机联调的单一入口。AGENTS.md 要求插件必须在 NAS 上的 MoviePilot Docker Compose 里
# 调试，而那台机器上有四个坑（完整说明见 docs/Repository_Guide.md 第 8 节）：
#
#   1. Python 真正 import 的是**容器内** /app/app/plugins/<id>/，宿主挂载点
#      /vol1/1000/Docker缓存/MoviePilot-v2/plugins/<id>/ 只是 MoviePilot 的安装位置。
#      只写一处，跑的还是旧代码 —— 所以 deploy 一次写两处。
#   2. 版本号比不出「同版本改了代码」，所以 ver 按文件内容算指纹。
#   3. tar 只覆盖不删除，所以 deploy 先清后铺，不然改名前的模块还留在那儿被 import。
#   4. 文件监控的热重载**不重绑 HTTP 路由**，也不换插件实例：接口仍指向已销毁实例的
#      bound method，内存态（锁、任务集、探针）全是僵尸的。所以改了 .py 默认重启容器，
#      只改 dist/ 前端产物才用 --no-restart。
#
# 用法：
#   scripts/nas.sh deploy <插件目录…> [--no-restart] [--force] [--wait 秒]
#   scripts/nas.sh ver [插件目录…]
#   scripts/nas.sh log <插件目录> [-n 行数] [-f [秒]]
#   scripts/nas.sh run [-q] <本地.py> [参数…]  用容器里的真运行时跑一段脚本（-q 滤宿主日志）
#   scripts/nas.sh replay <本地.py> [参数…]    等于 run -q，回放真实数据时用这个
#   scripts/nas.sh psql [<本地.sql>]          不带文件时从 stdin 读
#   scripts/nas.sh restart
#
# 插件目录用小写（checkin / p115liteassistant），Id 与版本从 package.json 反查。

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

SSH_HOST="${NAS_SSH_HOST:-nas}"
CONTAINER="${NAS_MP_CONTAINER:-moviepilot-v2}"
PG_CONTAINER="${NAS_PG_CONTAINER:-service-postgresql-1}"
HOST_PLUGINS="${NAS_HOST_PLUGINS:-/vol1/1000/Docker缓存/MoviePilot-v2/plugins}"
CONTAINER_PLUGINS=/app/app/plugins
PY=/opt/venv/bin/python
MP_LOG=/config/logs/moviepilot.log

die() { printf '\033[31m%s\033[0m\n' "$*" >&2; exit 1; }
info() { printf '\033[36m%s\033[0m\n' "$*"; }
ok() { printf '\033[32m%s\033[0m\n' "$*"; }

# 插件目录 → "Id<TAB>版本"，权威来源是 package.json（发布脚本也认它）
meta() {
  python - "$1" <<'PYEOF'
import io, json, sys
want = sys.argv[1].lower()
index = json.load(io.open("package.json", encoding="utf-8"))
for key, value in index.items():
    if key.lower() == want:
        print(key, value.get("version", ""), sep="\t")
        break
else:
    sys.exit(f"package.json 里没有插件 {want}")
PYEOF
}

# 运行时文件的选择器：只此一处定义，打包、指纹、清理三处共用 —— 三者口径不同时，
# 「部署完了指纹还对不上」这种假警报就没完没了。嵌套目录里的 .py 也会被列出来，
# 所以清理才敢按同一条口径整片删。
FP_FIND='find . -name __pycache__ -prune -o -type f \( -name "*.py" -o -name requirements.txt -o -path "./dist/*" \) -print'

pack_list() {
  local id="$1"
  ( cd "plugins/$id" 2>/dev/null && eval "$FP_FIND" ) | sed "s|^\./|$id/|"
}

# 插件运行时文件的指纹。版本号比不出「同版本改了代码」——开发中间态从来不升版本号，
# ver 只看 plugin_version 就会在容器跑着旧代码时报「一致」。这里按文件内容算，
# 两边用同一条 find 各自列文件，所以容器里残留的旧模块也会让指纹对不上。
# `sed` 那一段是必须的：Git Bash 的 sha256sum 按二进制模式打「<hash> *./path」，容器里的
# coreutils 打「<hash>  ./path」，差这一个星号就让两边指纹永远对不上。
FP_NORM='sed "s/^\([0-9a-f]\{64\}\) [ *]/\1  /"'
fp_cmd() { printf '%s | LC_ALL=C sort | xargs -r sha256sum | %s | sha256sum | cut -c1-12' "$FP_FIND" "$FP_NORM"; }

fp_local() {
  ( cd "plugins/$1" 2>/dev/null && eval "$(fp_cmd)" ) || echo '-'
}

# 容器里那几个插件的指纹，一次 SSH 取回，输出 "<id> <指纹>" 每行一个。
# 指纹命令自己带双引号，所以只能作为**单引号**环境变量送过去，不能拼进双引号命令串里 ——
# 拼进去的话内层引号会提前把外层字符串截断，命令静默变形、指纹恒为空。
fp_remote() {
  ssh "$SSH_HOST" \
      "MPC='$CONTAINER' CP='$CONTAINER_PLUGINS' IDS='$*' FPCMD='$(fp_cmd)' bash -s" <<'REMOTEEOF'
set -u
for id in $IDS; do
  printf '%s ' "$id"
  docker exec "$MPC" sh -lc "cd $CP/$id 2>/dev/null && $FPCMD" 2>/dev/null || echo '-'
done
REMOTEEOF
}

cmd_deploy() {
  local restart=1 wait_secs=90 force=0 ids=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --no-restart) restart=0 ;;
      --restart) restart=1 ;;
      --force) force=1 ;;
      --wait) shift; wait_secs="${1:?--wait 要给秒数}" ;;
      -*) die "未知参数 $1" ;;
      *) ids+=("$1") ;;
    esac
    shift
  done
  [ ${#ids[@]} -gt 0 ] || die "至少给一个插件目录"

  if [ "$force" = 0 ]; then
    # 指纹一致就跳过：重启容器要 30 秒，还会打断正在跑的任务，不该为一次空部署付这个价
    local remote_fps stale=()
    remote_fps="$(fp_remote "${ids[@]}")"
    for id in "${ids[@]}"; do
      local want have
      want="$(fp_local "$id")"
      have="$(printf '%s\n' "$remote_fps" | awk -v k="$id" '$1 == k { print $2 }')"
      if [ "$want" = "$have" ] && [ "$want" != '-' ]; then
        ok "$id 指纹已一致（$want），跳过"
      else
        stale+=("$id")
      fi
    done
    [ ${#stale[@]} -gt 0 ] || { ok '都是最新的，什么都没做（要强制重推加 --force）'; return 0; }
    ids=("${stale[@]}")
  fi

  local files=() specs=() id line plugin_id version
  for id in "${ids[@]}"; do
    [ -d "plugins/$id" ] || die "plugins/$id 不存在"
    line="$(meta "$id")"
    plugin_id="${line%%$'\t'*}"; version="${line#*$'\t'}"
    specs+=("$plugin_id=$version")
    while IFS= read -r entry; do files+=("$entry"); done < <(pack_list "$id")
    info "打包 $id → $plugin_id $version（指纹 $(fp_local "$id")）"
  done
  [ ${#files[@]} -gt 0 ] || die "没有可送的文件"

  # 一次 SSH 干完全部：收包 → 写宿主 → 写容器 → 清 pycache →（可选）重启并等版本行。
  # 本机的 ssh 不支持 ControlMaster，多开连接只是白付握手，所以远端脚本一次跑完。
  #
  # 远端脚本走 base64 参数、tar 包走 stdin：两样都塞 stdin 的话（`ssh … bash -s <<EOF`
  # 再往管道里灌 tar）heredoc 会顶掉管道，远端拿到的是脚本、`cat > $TGZ` 读到 EOF，
  # 于是「部署成功」但一个字节都没落地 —— 这个坑踩过一次。
  local remote_script
  remote_script="$(cat <<'REMOTEEOF'
set -eu
TGZ=$(mktemp /tmp/mpp-XXXXXX.tgz)
trap 'rm -f "$TGZ"' EXIT
cat > "$TGZ"
printf '收到 %s 字节\n' "$(wc -c < "$TGZ")"

# 先清后铺：清掉所有 .py 与整个 dist/（连空目录一起），index.html、package.json 这些
# 市场安装留下的文件不动。tar 只覆盖不删除，所以不先清的话，改名前的模块、上一版的
# remoteEntry、早年放在插件目录里的 tests/ 会一直躺在运行时副本里被 import。
PURGE='for id in $IDS; do
  [ -d "$id" ] || continue
  find "$id" -name "*.py" -delete 2>/dev/null || true
  rm -rf "$id/dist" 2>/dev/null || true
  find "$id" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
  find "$id" -mindepth 1 -type d -empty -delete 2>/dev/null || true
done'

for id in $IDS; do mkdir -p "$HOSTP/$id"; done
( cd "$HOSTP" && eval "$PURGE" )
tar -xzf "$TGZ" -C "$HOSTP"
echo "宿主机已更新：$HOSTP"

docker cp "$TGZ" "$MPC:/tmp/mpp-deploy.tgz" >/dev/null
docker exec -e IDS="$IDS" "$MPC" sh -lc "
  cd $CP || exit 1
  $PURGE
  tar -xzf /tmp/mpp-deploy.tgz
  rm -f /tmp/mpp-deploy.tgz
"
echo "容器已更新：$CP"

for id in $IDS; do
  printf '  %-20s 容器内 %s\n' "$id" \
    "$(docker exec "$MPC" sh -lc "grep -m1 plugin_version $CP/$id/__init__.py" | tr -d ' ' || echo '?')"
done

[ "$RESTART" = 1 ] || { echo '跳过重启（--no-restart）：只改 dist/ 时热重载够用，改了 .py 就必须重启'; exit 0; }

# 只认重启之后新写进来的那几行，不然「加载插件：Checkin 版本：1.7.0」会命中上一次的日志
BASE=$(docker exec "$MPC" sh -lc "wc -l < $MPLOG" | tr -d ' ')
echo "重启 $MPC（日志基线 ${BASE} 行）"
docker restart "$MPC" >/dev/null

END=$((SECONDS + WAIT))
while [ $SECONDS -lt $END ]; do
  sleep 3
  TAIL=$(docker exec "$MPC" sh -lc "tail -n +$((BASE + 1)) $MPLOG 2>/dev/null" || true)
  MISSING=
  for spec in $SPECS; do
    pid=${spec%%=*}; ver=${spec#*=}
    printf '%s' "$TAIL" | grep -aq "加载插件：$pid 版本：$ver" || MISSING="$MISSING $pid"
  done
  [ -n "$MISSING" ] || { echo "已加载：$SPECS"; exit 0; }
done
echo "等了 ${WAIT}s 仍未看到：$MISSING" >&2
echo "--- 重启后 ${MPLOG} 里与插件相关的行 ---" >&2
docker exec "$MPC" sh -lc "tail -n +$((BASE + 1)) $MPLOG | grep -aE '加载插件|插件.*失败|Traceback' | tail -n 20" >&2 || true
exit 1
REMOTEEOF
)"
  local b64
  b64="$(printf '%s' "$remote_script" | base64 -w0)"

  tar -C plugins -czf - \
      --exclude=__pycache__ --exclude='*.log' --exclude='notify-preview.txt' \
      "${files[@]}" \
    | ssh "$SSH_HOST" \
        "export MPC='$CONTAINER' HOSTP='$HOST_PLUGINS' CP='$CONTAINER_PLUGINS' MPLOG='$MP_LOG' \
                IDS='${ids[*]}' SPECS='${specs[*]}' RESTART=$restart WAIT=$wait_secs; \
         S=\$(mktemp /tmp/nas-deploy-XXXXXX.sh); printf '%s' '$b64' | base64 -d > \"\$S\"; \
         bash \"\$S\"; rc=\$?; rm -f \"\$S\"; exit \$rc"
  ok "deploy 完成"
}

cmd_ver() {
  local ids=("$@") id line plugin_id version
  if [ ${#ids[@]} -eq 0 ]; then
    mapfile -t ids < <(cd plugins && ls -d */ 2>/dev/null | sed 's|/$||')
  fi
  local specs=()
  for id in "${ids[@]}"; do
    line="$(meta "$id")"
    plugin_id="${line%%$'\t'*}"; version="${line#*$'\t'}"
    specs+=("$id:$plugin_id:$version:$(fp_local "$id")")
  done
  ssh "$SSH_HOST" \
      "MPC='$CONTAINER' HOSTP='$HOST_PLUGINS' CP='$CONTAINER_PLUGINS' MPLOG='$MP_LOG'" \
      "SPECS='${specs[*]}' FPCMD='$(fp_cmd)' bash -s" <<'REMOTEEOF'
set -eu
printf '%-20s %-8s %-8s %-8s %-13s %-13s %s\n' 插件 本地 宿主机 容器内 本地指纹 容器指纹 ''
for spec in $SPECS; do
  id=${spec%%:*}; rest=${spec#*:}; pid=${rest%%:*}; rest=${rest#*:}
  local_ver=${rest%%:*}; local_fp=${rest#*:}
  host_ver=$(sed -n 's/.*plugin_version *= *"\([^"]*\)".*/\1/p' "$HOSTP/$id/__init__.py" 2>/dev/null | head -1)
  cont_ver=$(docker exec "$MPC" sh -lc "sed -n 's/.*plugin_version *= *\"\([^\"]*\)\".*/\1/p' $CP/$id/__init__.py 2>/dev/null | head -1" || true)
  cont_fp=$(docker exec "$MPC" sh -lc "cd $CP/$id 2>/dev/null && $FPCMD" || echo '-')
  loaded=$(docker exec "$MPC" sh -lc "grep -a '加载插件：$pid 版本：' $MPLOG | tail -1 | sed 's/.*版本：//'" 2>/dev/null || true)
  mark=''
  [ "$local_fp" = "$cont_fp" ] || mark='! 要 deploy'
  [ "$local_ver" = "${loaded:-}" ] || mark="$mark${mark:+ /} 已加载 ${loaded:--}"
  printf '%-20s %-8s %-8s %-8s %-13s %-13s %s\n' \
    "$id" "${local_ver:--}" "${host_ver:--}" "${cont_ver:--}" "$local_fp" "$cont_fp" "$mark"
done
echo
echo '指纹按 .py / requirements.txt / dist 的内容算：版本号相同但指纹不同，说明容器跑的是旧代码'
REMOTEEOF
}

cmd_log() {
  local id="${1:?要给插件目录}"; shift || true
  local lines=40 follow=0 secs=60
  while [ $# -gt 0 ]; do
    case "$1" in
      -n) shift; lines="${1:?-n 要给行数}" ;;
      -f) follow=1; case "${2:-}" in ''|-*) ;; *) shift; secs="$1" ;; esac ;;
      *) die "未知参数 $1" ;;
    esac
    shift
  done
  local logfile="/config/logs/plugins/${id}.log"
  if [ "$follow" = 1 ]; then
    info "跟随 $logfile（${secs}s 后自动结束）"
    ssh "$SSH_HOST" "docker exec '$CONTAINER' sh -lc 'timeout $secs tail -n $lines -F $logfile'" || true
  else
    ssh "$SSH_HOST" "docker exec '$CONTAINER' sh -lc 'tail -n $lines $logfile'"
  fi
}

# 一个探针脚本 import app.plugins.* 就会把 MoviePilot 的半个启动流程带起来：飞书长连接、
# 插件文件监控、下载器连接，各自往 stdout 灌日志；退出时飞书那个 WS 线程还会在
# 「This event loop is already running」上炸一次、偶尔以 segfault 收场。这些都在探针
# 自己的输出之外，--quiet 把它们滤掉，只留脚本说的话。
RUN_NOISE='^(\x1b\[[0-9;]*m)*(INFO|WARNING|ERROR|DEBUG):|^\[Lark\]|PostgreSQL database connected|RuntimeWarning|Enable tracemalloc|feishu\.py|_run_ws_client|_shutdown_ws_client|This event loop is already running|_invoke_excepthook|^Exception in thread|^Traceback \(most recent call last\):$|^  File "/usr/local/lib/python3\.12/(threading|asyncio)|^    (self\.run\(\)|self\._target|loop\.run_until_complete|self\._check_running\(\)|raise RuntimeError)|^Segmentation fault'

cmd_run() {
  local quiet=0
  if [ "${1:-}" = "--quiet" ] || [ "${1:-}" = "-q" ]; then quiet=1; shift; fi
  local script="${1:?要给一个本地 .py}"; shift || true
  [ -f "$script" ] || die "$script 不存在"
  info "在容器里跑 $(basename "$script")（cwd=/app，解释器 $PY${quiet:+，已滤掉宿主日志}）"
  # 脚本走 stdin 进容器，不落宿主机；用真运行时导入 app.* 与 app.plugins.*
  local rc=0
  if [ "$quiet" = 1 ]; then
    ssh "$SSH_HOST" \
      "docker exec -i '$CONTAINER' sh -lc 'cd /app && cat > /tmp/nas-run.py && $PY /tmp/nas-run.py $*; rc=\$?; rm -f /tmp/nas-run.py; exit \$rc'" \
      < "$script" 2>&1 | grep -avE "$RUN_NOISE" || rc=$?
  else
    ssh "$SSH_HOST" \
      "docker exec -i '$CONTAINER' sh -lc 'cd /app && cat > /tmp/nas-run.py && $PY /tmp/nas-run.py $*; rc=\$?; rm -f /tmp/nas-run.py; exit \$rc'" \
      < "$script" || rc=$?
  fi
  [ "$rc" = 139 ] && info '（退出码 139：飞书 WS 线程在解释器收尾时炸的，脚本本身已经跑完）'
  return 0
}

cmd_psql() {
  local sql="${1:-}"
  # 密码不落盘：从 MoviePilot 容器的环境变量里取，只在远端 shell 内传递
  local remote="PGPW=\$(docker inspect '$CONTAINER' --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^DB_POSTGRESQL_PASSWORD=//p')
docker exec -i -e PGPASSWORD=\"\$PGPW\" '$PG_CONTAINER' psql -U moviepilot -d moviepilot -p 5432 -v ON_ERROR_STOP=1"
  if [ -n "$sql" ]; then
    [ -f "$sql" ] || die "$sql 不存在"
    ssh "$SSH_HOST" "$remote" < "$sql"
  else
    ssh "$SSH_HOST" "$remote"
  fi
}

cmd_restart() {
  info "重启 $CONTAINER"
  ssh "$SSH_HOST" "docker restart '$CONTAINER' >/dev/null && for i in \$(seq 30); do
      s=\$(docker inspect --format '{{.State.Health.Status}}' '$CONTAINER' 2>/dev/null || echo none)
      [ \"\$s\" = healthy ] && { echo healthy; exit 0; }
      sleep 3
    done; echo '等了 90s 还没 healthy' >&2; exit 1"
}

case "${1:-}" in
  deploy)  shift; cmd_deploy "$@" ;;
  ver)     shift; cmd_ver "$@" ;;
  log)     shift; cmd_log "$@" ;;
  run)     shift; cmd_run "$@" ;;
  replay)  shift; cmd_run --quiet "$@" ;;
  psql)    shift; cmd_psql "$@" ;;
  restart) shift; cmd_restart "$@" ;;
  ''|-h|--help|help)
    # 头部注释就是帮助文本：打到第一行非注释为止，别写死行号
    awk 'NR > 1 { if (/^#/) { sub(/^# ?/, ""); print } else { exit } }' "${BASH_SOURCE[0]}" ;;
  *) die "未知命令 ${1}；用 scripts/nas.sh --help 看用法" ;;
esac
