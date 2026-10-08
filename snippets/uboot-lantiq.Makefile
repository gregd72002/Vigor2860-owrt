define U-Boot/vigor2860_ram
  NAME:=DrayTek Vigor 2860 (RAM, Drayboot chainload)
  BUILD_SUBTARGET:=xrx200
  SOC:=vr9
  DDR_SETTINGS:=board/draytek/vigor2860/ddr_settings.h
endef

UBOOT_TARGETS:= \
	vigor2860_ram \
