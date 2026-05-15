#!/bin/bash
set -e

NFS_SERVER="10.1.1.26"
NFS_PATH="/"
MOUNT_POINT="/file_storage"

echo "[INFO] Creating mount point: $MOUNT_POINT"
mkdir -p "$MOUNT_POINT"

echo "[INFO] Mounting NFS: $NFS_SERVER:$NFS_PATH to $MOUNT_POINT"
mount -t nfs -o vers=4,rw,soft,retrans=3 "$NFS_SERVER:$NFS_PATH" "$MOUNT_POINT" 2>&1

if [ $? -eq 0 ]; then
    echo "[SUCCESS] NFS mounted successfully"
    echo "[INFO] Mount info:"
    mount | grep "$MOUNT_POINT"
    echo "[INFO] NFS contents:"
    ls -la "$MOUNT_POINT" | head -20
else
    echo "[ERROR] Failed to mount NFS - trying to list available exports..."
    echo "[INFO] Available NFS shares:"
    timeout 3 showmount -e "$NFS_SERVER" 2>&1 || echo "Could not list exports"
    exit 1
fi

echo "[INFO] Starting application..."
exec python main.py
