// NeoOS UEFI loader: loads kernel.elf from the ESP, copies its PT_LOAD
// segments to their physical addresses, exits boot services, turns the
// MMU off, and jumps to the kernel entry. Built with gnu-efi.
#include <efi.h>
#include <efilib.h>

// Minimal ELF64 structures (avoid host <elf.h> quirks under gnu-efi flags).
struct elf64_ehdr {
    UINT8 e_ident[16];
    UINT16 e_type, e_machine;
    UINT32 e_version;
    UINT64 e_entry, e_phoff, e_shoff;
    UINT32 e_flags;
    UINT16 e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, e_shstrndx;
};
struct elf64_phdr {
    UINT32 p_type, p_flags;
    UINT64 p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align;
};

EFI_STATUS EFIAPI efi_main(EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable) {
    InitializeLib(ImageHandle, SystemTable);

    EFI_STATUS status;
    EFI_LOADED_IMAGE *loaded = NULL;
    status = BS->OpenProtocol(ImageHandle, &gEfiLoadedImageProtocolGuid,
                              (VOID **)&loaded, ImageHandle, NULL,
                              EFI_OPEN_PROTOCOL_GET_PROTOCOL);
    if (EFI_ERROR(status)) { Print(L"loader: no LoadedImage\r\n"); return status; }

    EFI_FILE_IO_INTERFACE *fs = NULL;
    status = BS->OpenProtocol(loaded->DeviceHandle, &gEfiSimpleFileSystemProtocolGuid,
                              (VOID **)&fs, ImageHandle, NULL,
                              EFI_OPEN_PROTOCOL_GET_PROTOCOL);
    if (EFI_ERROR(status)) { Print(L"loader: no SimpleFileSystem\r\n"); return status; }

    EFI_FILE_HANDLE root = NULL;
    status = fs->OpenVolume(fs, &root);
    if (EFI_ERROR(status)) { Print(L"loader: OpenVolume failed\r\n"); return status; }

    EFI_FILE_HANDLE file = NULL;
    status = root->Open(root, &file, L"\\kernel.elf", EFI_FILE_MODE_READ, 0);
    if (EFI_ERROR(status)) { Print(L"loader: kernel.elf not found\r\n"); return status; }

    // File size via GetInfo.
    UINT8 info_buf[256];
    UINTN info_size = sizeof(info_buf);
    status = file->GetInfo(file, &gEfiFileInfoGuid, &info_size, info_buf);
    if (EFI_ERROR(status)) { Print(L"loader: GetInfo failed\r\n"); return status; }
    EFI_FILE_INFO *info = (EFI_FILE_INFO *)info_buf;
    UINTN file_size = (UINTN)info->FileSize;

    UINT8 *buf = AllocatePool(file_size);
    if (!buf) { Print(L"loader: AllocatePool failed\r\n"); return EFI_OUT_OF_RESOURCES; }
    UINTN read_size = file_size;
    status = file->Read(file, &read_size, buf);
    if (EFI_ERROR(status) || read_size != file_size) { Print(L"loader: Read failed\r\n"); return status; }
    file->Close(file);

    struct elf64_ehdr *eh = (struct elf64_ehdr *)buf;
    if (eh->e_ident[0] != 0x7F || eh->e_ident[1] != 'E' || eh->e_ident[2] != 'L' ||
        eh->e_ident[3] != 'F' || eh->e_machine != 0xB7) {
        Print(L"loader: not an AArch64 ELF\r\n");
        return EFI_LOAD_ERROR;
    }
    Print(L"loader: kernel.elf %d bytes, entry %lx\r\n", (UINT64)file_size, eh->e_entry);

    for (int i = 0; i < eh->e_phnum; i++) {
        struct elf64_phdr *ph = (struct elf64_phdr *)(buf + eh->e_phoff + i * eh->e_phentsize);
        if (ph->p_type != 1) continue; // PT_LOAD
        UINT8 *dest = (UINT8 *)(UINTN)ph->p_paddr;
        UINT8 *src = buf + ph->p_offset;
        for (UINT64 j = 0; j < ph->p_filesz; j++) dest[j] = src[j];
        for (UINT64 j = ph->p_filesz; j < ph->p_memsz; j++) dest[j] = 0;
    }
    UINT64 entry = eh->e_entry;
    FreePool(buf);

    // ExitBootServices: get the memory map, then exit (retry once on map change).
    UINTN map_size = 0, map_key = 0, desc_size = 0;
    UINT32 desc_ver = 0;
    BS->GetMemoryMap(&map_size, NULL, &map_key, &desc_size, &desc_ver);
    map_size += 8 * desc_size;
    EFI_MEMORY_DESCRIPTOR *map = AllocatePool(map_size);
    status = BS->GetMemoryMap(&map_size, map, &map_key, &desc_size, &desc_ver);
    if (EFI_ERROR(status)) { Print(L"loader: GetMemoryMap failed\r\n"); return status; }
    status = BS->ExitBootServices(ImageHandle, map_key);
    if (EFI_ERROR(status)) {
        BS->GetMemoryMap(&map_size, map, &map_key, &desc_size, &desc_ver);
        status = BS->ExitBootServices(ImageHandle, map_key);
        if (EFI_ERROR(status)) return status;
    }

    // Firmware ran with the MMU on (identity-mapped on QEMU virt): turn it off
    // so the kernel sees the same bare environment as QEMU -kernel boot.
    __asm__ volatile(
        "mrs x0, sctlr_el1\n"
        "bic x0, x0, #1\n"
        "bic x0, x0, #4\n"
        "bic x0, x0, #0x1000\n"
        "msr sctlr_el1, x0\n"
        "tlbi vmalle1\n"
        "dsb sy\n"
        "isb\n"
        ::: "x0", "memory");

    ((void (*)(void))(UINTN)entry)();
    return EFI_SUCCESS; // never reached
}
