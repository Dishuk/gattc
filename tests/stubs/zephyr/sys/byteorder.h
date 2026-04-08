#ifndef ZEPHYR_SYS_BYTEORDER_H
#define ZEPHYR_SYS_BYTEORDER_H

#include <stdint.h>

#define sys_cpu_to_le16(x) ((uint16_t)(x))
#define sys_cpu_to_le32(x) ((uint32_t)(x))
#define sys_le16_to_cpu(x) ((uint16_t)(x))
#define sys_le32_to_cpu(x) ((uint32_t)(x))
#define sys_cpu_to_be16(x) ((uint16_t)(x))
#define sys_cpu_to_be32(x) ((uint32_t)(x))
#define sys_be16_to_cpu(x) ((uint16_t)(x))
#define sys_be32_to_cpu(x) ((uint32_t)(x))
#define sys_cpu_to_le64(x) ((uint64_t)(x))
#define sys_cpu_to_be64(x) ((uint64_t)(x))
#define sys_le64_to_cpu(x) ((uint64_t)(x))
#define sys_be64_to_cpu(x) ((uint64_t)(x))

#endif
