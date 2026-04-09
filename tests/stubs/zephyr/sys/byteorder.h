#ifndef ZEPHYR_SYS_BYTEORDER_H
#define ZEPHYR_SYS_BYTEORDER_H

#include <stdint.h>

/* Real byte-swap helpers (standard C bit manipulation) */
#define _gattc_bswap16(x) ((uint16_t)(((uint16_t)(x) >> 8) | ((uint16_t)(x) << 8)))
#define _gattc_bswap32(x) ((uint32_t)( \
    (((uint32_t)(x) & 0xFF000000u) >> 24) | \
    (((uint32_t)(x) & 0x00FF0000u) >>  8) | \
    (((uint32_t)(x) & 0x0000FF00u) <<  8) | \
    (((uint32_t)(x) & 0x000000FFu) << 24)))
#define _gattc_bswap64(x) ((uint64_t)( \
    (((uint64_t)(x) & 0xFF00000000000000ull) >> 56) | \
    (((uint64_t)(x) & 0x00FF000000000000ull) >> 40) | \
    (((uint64_t)(x) & 0x0000FF0000000000ull) >> 24) | \
    (((uint64_t)(x) & 0x000000FF00000000ull) >>  8) | \
    (((uint64_t)(x) & 0x00000000FF000000ull) <<  8) | \
    (((uint64_t)(x) & 0x0000000000FF0000ull) << 24) | \
    (((uint64_t)(x) & 0x000000000000FF00ull) << 40) | \
    (((uint64_t)(x) & 0x00000000000000FFull) << 56)))

/* LE = identity (test hosts are little-endian) */
#define sys_cpu_to_le16(x) ((uint16_t)(x))
#define sys_cpu_to_le32(x) ((uint32_t)(x))
#define sys_cpu_to_le64(x) ((uint64_t)(x))
#define sys_le16_to_cpu(x) ((uint16_t)(x))
#define sys_le32_to_cpu(x) ((uint32_t)(x))
#define sys_le64_to_cpu(x) ((uint64_t)(x))

/* BE = real byte swap */
#define sys_cpu_to_be16(x) _gattc_bswap16(x)
#define sys_cpu_to_be32(x) _gattc_bswap32(x)
#define sys_cpu_to_be64(x) _gattc_bswap64(x)
#define sys_be16_to_cpu(x) _gattc_bswap16(x)
#define sys_be32_to_cpu(x) _gattc_bswap32(x)
#define sys_be64_to_cpu(x) _gattc_bswap64(x)

#endif
