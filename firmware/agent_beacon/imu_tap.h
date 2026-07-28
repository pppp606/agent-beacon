#pragma once
#include <stdint.h>

#include "nrf_gpio.h"

// Double-tap detection on the XIAO nRF52840 Sense's LSM6DS3TR-C IMU.
//
// Hardware glue only — what a tap *means* is decided by the sketch
// (ADR 0003: no protocol decisions outside attention_state.h / the sketch).
//
// Wiring facts, confirmed against the official Zephyr devicetree
// (zephyr/boards/seeed/xiao_ble): SDA=P0.07, SCL=P0.27, INT1=P0.11, and the
// IMU is powered from GPIO P1.08 which MUST be driven in high-drive mode
// (NRF_GPIO_DRIVE_S0H1) — standard drive cannot supply the chip, which then
// browns out and wedges the I2C bus. That failure mode also hangs the Wire
// library, so this file bit-bangs I2C with every loop bounded instead.
//
// The detection itself runs inside the IMU (ST AN5130): we configure the
// double-tap engine once, then merely poll the latched INT1 line and clear
// it by reading TAP_SRC. On a plain XIAO (no IMU) begin() fails the
// WHO_AM_I check and the feature stays disabled — same binary everywhere.

static const uint32_t IMU_PIN_SDA = NRF_GPIO_PIN_MAP(0, 7);
static const uint32_t IMU_PIN_SCL = NRF_GPIO_PIN_MAP(0, 27);
static const uint32_t IMU_PIN_INT1 = NRF_GPIO_PIN_MAP(0, 11);
static const uint32_t IMU_PIN_POWER = NRF_GPIO_PIN_MAP(1, 8);

static const uint8_t IMU_ADDR = 0x6A;
static const uint8_t IMU_WHO_AM_I_VALUE = 0x6A;  // LSM6DS3TR-C

static const uint8_t IMU_REG_WHO_AM_I = 0x0F;
static const uint8_t IMU_REG_CTRL1_XL = 0x10;
static const uint8_t IMU_REG_TAP_SRC = 0x1C;
static const uint8_t IMU_REG_TAP_CFG = 0x58;
static const uint8_t IMU_REG_TAP_THS_6D = 0x59;
static const uint8_t IMU_REG_INT_DUR2 = 0x5A;
static const uint8_t IMU_REG_WAKE_UP_THS = 0x5B;
static const uint8_t IMU_REG_MD1_CFG = 0x5E;

// ---------- bounded open-drain bit-bang I2C ----------

static void imuPinLow(uint32_t pin) {
  nrf_gpio_pin_clear(pin);
  nrf_gpio_cfg_output(pin);
}

static void imuPinRelease(uint32_t pin) {
  nrf_gpio_cfg_input(pin, NRF_GPIO_PIN_PULLUP);
}

static bool imuSclHigh() {  // honors clock stretching, bounded
  imuPinRelease(IMU_PIN_SCL);
  for (int i = 0; i < 1000; i++) {
    if (nrf_gpio_pin_read(IMU_PIN_SCL)) return true;
    delayMicroseconds(1);
  }
  return false;
}

static bool imuClock(bool* sdaValue) {
  delayMicroseconds(5);
  if (!imuSclHigh()) return false;
  delayMicroseconds(5);
  if (sdaValue != nullptr) *sdaValue = nrf_gpio_pin_read(IMU_PIN_SDA);
  imuPinLow(IMU_PIN_SCL);
  delayMicroseconds(5);
  return true;
}

static bool imuStart() {
  imuPinRelease(IMU_PIN_SDA);
  if (!imuSclHigh()) return false;
  delayMicroseconds(5);
  imuPinLow(IMU_PIN_SDA);
  delayMicroseconds(5);
  imuPinLow(IMU_PIN_SCL);
  return true;
}

static void imuStopCond() {
  imuPinLow(IMU_PIN_SDA);
  delayMicroseconds(5);
  imuSclHigh();
  delayMicroseconds(5);
  imuPinRelease(IMU_PIN_SDA);
  delayMicroseconds(5);
}

static bool imuWriteByte(uint8_t value) {  // returns true iff ACKed
  for (int bit = 7; bit >= 0; bit--) {
    if (value & (1 << bit)) imuPinRelease(IMU_PIN_SDA);
    else imuPinLow(IMU_PIN_SDA);
    if (!imuClock(nullptr)) return false;
  }
  imuPinRelease(IMU_PIN_SDA);
  bool sda = true;
  if (!imuClock(&sda)) return false;
  return !sda;
}

static bool imuReadByteNack(uint8_t* out) {
  uint8_t value = 0;
  imuPinRelease(IMU_PIN_SDA);
  for (int bit = 0; bit < 8; bit++) {
    bool sda = false;
    if (!imuClock(&sda)) return false;
    value = (uint8_t)((value << 1) | (sda ? 1 : 0));
  }
  imuPinRelease(IMU_PIN_SDA);  // NACK: final byte
  if (!imuClock(nullptr)) return false;
  *out = value;
  return true;
}

static bool imuWriteReg(uint8_t reg, uint8_t value) {
  if (!imuStart()) return false;
  bool ok = imuWriteByte((uint8_t)(IMU_ADDR << 1)) && imuWriteByte(reg)
            && imuWriteByte(value);
  imuStopCond();
  return ok;
}

static bool imuReadReg(uint8_t reg, uint8_t* out) {
  if (!imuStart()) return false;
  bool ok = imuWriteByte((uint8_t)(IMU_ADDR << 1)) && imuWriteByte(reg);
  if (ok) {
    ok = imuStart() && imuWriteByte((uint8_t)((IMU_ADDR << 1) | 1))
         && imuReadByteNack(out);
  }
  imuStopCond();
  return ok;
}

// ---------- public API ----------
//
// Power gating: tap detection at 416Hz costs ~170µA, but a tap is only
// meaningful while the display is lit — so the sketch powers the IMU rail
// on when the display lights and cuts it when it goes dark. Probe once at
// boot to learn whether the board has an IMU at all.

static void imuRailOn() {
  // High drive is mandatory: the chip is powered from this GPIO and browns
  // out under standard drive (official devicetree: NRF_GPIO_DRIVE_S0H1)
  nrf_gpio_cfg(IMU_PIN_POWER, NRF_GPIO_PIN_DIR_OUTPUT,
               NRF_GPIO_PIN_INPUT_DISCONNECT, NRF_GPIO_PIN_NOPULL,
               NRF_GPIO_PIN_S0H1, NRF_GPIO_PIN_NOSENSE);
  nrf_gpio_pin_set(IMU_PIN_POWER);
  delay(50);  // chip boot time is ~35ms
  imuPinRelease(IMU_PIN_SDA);
  imuPinRelease(IMU_PIN_SCL);
  nrf_gpio_cfg_input(IMU_PIN_INT1, NRF_GPIO_PIN_PULLDOWN);
  delay(5);
}

// Cuts the IMU power rail. Bus pins go no-pull: a pull-up would leak
// current into the unpowered chip through its I/O pins.
static void imuTapPowerOff() {
  nrf_gpio_pin_clear(IMU_PIN_POWER);
  nrf_gpio_cfg_input(IMU_PIN_SDA, NRF_GPIO_PIN_NOPULL);
  nrf_gpio_cfg_input(IMU_PIN_SCL, NRF_GPIO_PIN_NOPULL);
}

// Boot-time check: does this board have the IMU? Leaves the rail off.
static bool imuTapProbe() {
  imuRailOn();
  uint8_t who = 0;
  bool present = imuReadReg(IMU_REG_WHO_AM_I, &who) && who == IMU_WHO_AM_I_VALUE;
  imuTapPowerOff();
  return present;
}

// Powers the IMU and arms its double-tap engine (config registers are
// volatile, so they are rewritten on every power-up).
static bool imuTapPowerOn() {
  imuRailOn();
  // Double-tap engine per ST AN5130
  bool ok = true;
  ok = ok && imuWriteReg(IMU_REG_CTRL1_XL, 0x60);     // accel 416Hz, ±2g
  ok = ok && imuWriteReg(IMU_REG_TAP_CFG, 0x8F);      // interrupts + tap X/Y/Z + latched INT
  ok = ok && imuWriteReg(IMU_REG_TAP_THS_6D, 0x0C);   // tap threshold (~750mg)
  ok = ok && imuWriteReg(IMU_REG_INT_DUR2, 0x7F);     // dur/quiet/shock windows
  ok = ok && imuWriteReg(IMU_REG_WAKE_UP_THS, 0x80);  // double-tap mode
  ok = ok && imuWriteReg(IMU_REG_MD1_CFG, 0x08);      // route double-tap to INT1
  if (!ok) imuTapPowerOff();
  return ok;
}

// True once per detected double-tap. INT1 is latched by the IMU; reading
// TAP_SRC both confirms the cause and releases the latch.
static bool imuTapPending() {
  if (!nrf_gpio_pin_read(IMU_PIN_INT1)) return false;
  uint8_t src = 0;
  if (!imuReadReg(IMU_REG_TAP_SRC, &src)) return false;
  return (src & 0x10) != 0;  // DOUBLE_TAP flag
}
