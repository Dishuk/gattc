#ifndef ZEPHYR_BLUETOOTH_GATT_H
#define ZEPHYR_BLUETOOTH_GATT_H

#include <stdint.h>
#include <stddef.h>
#include <sys/types.h>

#ifndef __packed
#define __packed __attribute__((packed))
#endif

struct bt_conn;
struct bt_gatt_attr;

#define BT_GATT_CHRC_READ              0x02
#define BT_GATT_CHRC_WRITE             0x08
#define BT_GATT_CHRC_WRITE_WITHOUT_RESP 0x04
#define BT_GATT_CHRC_NOTIFY            0x10
#define BT_GATT_CHRC_INDICATE          0x20

#define BT_GATT_PERM_READ              0x01
#define BT_GATT_PERM_WRITE             0x02
#define BT_GATT_PERM_READ_ENCRYPT      0x04
#define BT_GATT_PERM_WRITE_ENCRYPT     0x08
#define BT_GATT_PERM_READ_AUTHEN       0x10
#define BT_GATT_PERM_WRITE_AUTHEN      0x20

#define BT_GATT_SERVICE_DEFINE(name, ...)
#define BT_GATT_PRIMARY_SERVICE(uuid)
#define BT_GATT_CHARACTERISTIC(uuid, props, perms, read_cb, write_cb, value)
#define BT_GATT_CCC(changed_cb, perms)

#endif
