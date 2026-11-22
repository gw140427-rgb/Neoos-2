CC = aarch64-linux-gnu-gcc
LD = aarch64-linux-gnu-ld
CFLAGS = -ffreestanding -nostdlib -Wall -O2 -mgeneral-regs-only

all: kernel.elf

boot.o: boot.S
	$(CC) $(CFLAGS) -c boot.S -o boot.o

vectors.o: vectors.S
	$(CC) $(CFLAGS) -c vectors.S -o vectors.o

kernel.o: kernel.c
	$(CC) $(CFLAGS) -c kernel.c -o kernel.o

kernel.elf: boot.o kernel.o vectors.o linker.ld
	$(LD) -T linker.ld -o kernel.elf boot.o kernel.o vectors.o

run: kernel.elf
	qemu-system-aarch64 -machine virt -cpu cortex-a57 -nographic -kernel kernel.elf

run-gui: kernel.elf
	qemu-system-aarch64 -machine virt -cpu cortex-a57 -m 128 -kernel kernel.elf -device ramfb -device virtio-tablet-device -device virtio-keyboard-device -display vnc=:99 -serial mon:stdio

clean:
	rm -f *.o kernel.elf
