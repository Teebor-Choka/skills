#!/bin/sh
# B4b: copy the staged files to one stick, then compare. Usage: b4-copy.sh backup|public
#   backup -> BACKUP stick (encrypted bundle). public -> PUBLIC stick (public key and record).
# Run once per stick, with only that stick in the USB-C port. B4 is done when both ran.
. "$(dirname "$0")/lib.sh"
need_done B4a
stage="$YKHK_STATE/stage"
case ${1-} in
backup)
  dir=${YKHK_BACKUP_DIR:-/media/amnesia/BACKUP}
  files="identity-backup.tar.gpg"
  ;;
public)
  dir=${YKHK_PUBLIC_DIR:-/media/amnesia/PUBLIC}
  files="public.asc ceremony-record.txt"
  ;;
*) die "usage: b4-copy.sh backup|public" ;;
esac
[ -d "$dir" ] && [ -w "$dir" ] || die "$dir is missing or not writable. Plug in and unlock the stick."
for f in $files; do cp "$stage/$f" "$dir/$f" || die "copy of $f failed"; done
sync
for f in $files; do cmp -s "$stage/$f" "$dir/$f" || die "$f differs after copy"; done
say "Copied and verified in $dir: $files"
mark_done "B4.$1"
if [ -f "$YKHK_STATE/done.B4.backup" ] && [ -f "$YKHK_STATE/done.B4.public" ]; then
  mark_done B4
  say "B4 done."
fi
