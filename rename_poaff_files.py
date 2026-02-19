#!/usr/bin/env python3
"""
POAFF Output Files Renamer

This script renames all files in the POAFF output directory by replacing
the 'global' prefix with a custom prefix specified by the user.

Usage:
    python rename_poaff_files.py <new_prefix> [options]

Examples:
    # Preview changes without applying them
    python rename_poaff_files.py custom --dry-run
    
    # Rename all files from 'global@' to 'custom@'
    python rename_poaff_files.py custom
    
    # Specify a custom output directory
    python rename_poaff_files.py custom --path /path/to/output/_POAFF
    
    # Specify a different old prefix to replace
    python rename_poaff_files.py custom --old-prefix global

Author: POAFF Project
Date: February 2026
"""

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Tuple, List


# Constants
DEFAULT_OLD_PREFIX = "global"
SEPARATOR = "@"
DEFAULT_OUTPUT_DIR = "docker_output/_POAFF"


class FileRenamer:
    """Handles the renaming of POAFF output files with a new prefix."""
    
    def __init__(self, old_prefix: str, new_prefix: str, base_path: Path, dry_run: bool = False):
        """
        Initialize the FileRenamer.
        
        Args:
            old_prefix: The current prefix to replace (e.g., 'global')
            new_prefix: The new prefix to use
            base_path: Path to the output directory
            dry_run: If True, only show what would be renamed without actually renaming
        """
        self.old_prefix = old_prefix
        self.new_prefix = new_prefix
        self.base_path = base_path
        self.dry_run = dry_run
        self.renamed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        self.errors: List[Tuple[str, str]] = []
    
    def validate_prefix(self, prefix: str) -> bool:
        """
        Validate that the prefix contains only allowed characters.
        
        Args:
            prefix: The prefix to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Allow alphanumeric, underscore, and hyphen
        pattern = r'^[a-zA-Z0-9_-]+$'
        return bool(re.match(pattern, prefix))
    
    def get_files_to_rename(self) -> List[Path]:
        """
        Get all files that need to be renamed.
        
        Returns:
            List of Path objects for files starting with old_prefix
        """
        files_to_rename = []
        prefix_pattern = f"{self.old_prefix}{SEPARATOR}"
        
        # Search in base directory
        if self.base_path.exists():
            for file_path in self.base_path.rglob('*'):
                if file_path.is_file() and file_path.name.startswith(prefix_pattern):
                    files_to_rename.append(file_path)
        
        return sorted(files_to_rename)
    
    def generate_new_name(self, old_path: Path) -> Path:
        """
        Generate the new file path with the new prefix.
        
        Args:
            old_path: Original file path
            
        Returns:
            New file path with updated prefix
        """
        old_name = old_path.name
        prefix_pattern = f"{self.old_prefix}{SEPARATOR}"
        new_prefix_pattern = f"{self.new_prefix}{SEPARATOR}"
        
        # Replace the old prefix with the new prefix
        new_name = old_name.replace(prefix_pattern, new_prefix_pattern, 1)
        new_path = old_path.parent / new_name
        
        return new_path
    
    def rename_file(self, old_path: Path, new_path: Path) -> bool:
        """
        Rename a single file.
        
        Args:
            old_path: Current file path
            new_path: Target file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if new_path.exists():
                print(f"  ⚠️  Target already exists: {new_path.name}")
                self.skipped_count += 1
                return False
            
            if not self.dry_run:
                old_path.rename(new_path)
            
            self.renamed_count += 1
            return True
            
        except PermissionError as e:
            error_msg = f"Permission denied: {e}"
            self.errors.append((str(old_path), error_msg))
            self.failed_count += 1
            return False
        except OSError as e:
            error_msg = f"OS error: {e}"
            self.errors.append((str(old_path), error_msg))
            self.failed_count += 1
            return False
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            self.errors.append((str(old_path), error_msg))
            self.failed_count += 1
            return False
    
    def process_files(self) -> None:
        """Process all files and rename them."""
        files = self.get_files_to_rename()
        
        if not files:
            print(f"\n✓ No files found with prefix '{self.old_prefix}{SEPARATOR}' in {self.base_path}")
            return
        
        print(f"\n{'[DRY RUN] ' if self.dry_run else ''}Found {len(files)} file(s) to process:\n")
        
        for old_path in files:
            new_path = self.generate_new_name(old_path)
            
            # Get relative paths for cleaner display
            try:
                rel_old = old_path.relative_to(self.base_path)
                rel_new = new_path.relative_to(self.base_path)
            except ValueError:
                rel_old = old_path
                rel_new = new_path
            
            status = "→" if not self.dry_run else "→ WOULD RENAME"
            print(f"  {rel_old}")
            print(f"    {status} {rel_new}")
            
            if self.dry_run:
                # In dry-run mode, just count as renamed (would be renamed)
                if not new_path.exists():
                    self.renamed_count += 1
                else:
                    self.skipped_count += 1
                    print(f"    ⊘ Would skip (target exists)")
            else:
                success = self.rename_file(old_path, new_path)
                if success:
                    print(f"    ✓ Renamed successfully")
                elif not success and new_path.exists():
                    print(f"    ⊘ Skipped (target exists)")
                else:
                    print(f"    ✗ Failed")
            print()
    
    def print_summary(self) -> None:
        """Print a summary of the renaming operation."""
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        
        if self.dry_run:
            print(f"Mode:           DRY RUN (no changes made)")
        else:
            print(f"Mode:           EXECUTE")
        
        print(f"Old prefix:     {self.old_prefix}{SEPARATOR}")
        print(f"New prefix:     {self.new_prefix}{SEPARATOR}")
        print(f"Directory:      {self.base_path}")
        
        rename_label = "Would rename:  " if self.dry_run else "Renamed:       "
        skip_label = "Would skip:    " if self.dry_run else "Skipped:       "
        
        print(f"\n{rename_label} {self.renamed_count}")
        print(f"{skip_label} {self.skipped_count}")
        print(f"Failed:         {self.failed_count}")
        
        if self.errors:
            print(f"\n{'='*60}")
            print("ERRORS")
            print("="*60)
            for file_path, error_msg in self.errors:
                print(f"\n{file_path}")
                print(f"  Error: {error_msg}")
        
        print("="*60 + "\n")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Rename POAFF output files by replacing the prefix.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes without applying them
  python rename_poaff_files.py custom --dry-run
  
  # Rename all files from 'global@' to 'custom@'
  python rename_poaff_files.py custom
  
  # Specify a custom output directory
  python rename_poaff_files.py sia2024 --path /path/to/output/_POAFF
  
  # Replace a different old prefix
  python rename_poaff_files.py new_prefix --old-prefix old_prefix
        """
    )
    
    parser.add_argument(
        'new_prefix',
        type=str,
        help='New prefix to replace the old prefix (alphanumeric, underscore, hyphen only)'
    )
    
    parser.add_argument(
        '--old-prefix',
        type=str,
        default=DEFAULT_OLD_PREFIX,
        help=f'Old prefix to replace (default: {DEFAULT_OLD_PREFIX})'
    )
    
    parser.add_argument(
        '--path',
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help=f'Path to the output directory (default: {DEFAULT_OUTPUT_DIR})'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without actually renaming files'
    )
    
    args = parser.parse_args()
    
    # Determine base path (support both relative and absolute paths)
    if Path(args.path).is_absolute():
        base_path = Path(args.path)
    else:
        # Assume relative to script location or current working directory
        script_dir = Path(__file__).parent
        base_path = script_dir / args.path
    
    # Validate directory exists
    if not base_path.exists():
        print(f"✗ Error: Directory does not exist: {base_path}")
        print(f"\nPlease ensure the path is correct or use --path to specify a different directory.")
        sys.exit(1)
    
    if not base_path.is_dir():
        print(f"✗ Error: Path is not a directory: {base_path}")
        sys.exit(1)
    
    # Create renamer instance
    renamer = FileRenamer(
        old_prefix=args.old_prefix,
        new_prefix=args.new_prefix,
        base_path=base_path,
        dry_run=args.dry_run
    )
    
    # Validate new prefix
    if not renamer.validate_prefix(args.new_prefix):
        print(f"✗ Error: Invalid prefix '{args.new_prefix}'")
        print(f"  Prefix must contain only alphanumeric characters, underscores, or hyphens.")
        sys.exit(1)
    
    # Validate old prefix
    if not renamer.validate_prefix(args.old_prefix):
        print(f"✗ Error: Invalid old prefix '{args.old_prefix}'")
        print(f"  Prefix must contain only alphanumeric characters, underscores, or hyphens.")
        sys.exit(1)
    
    # Check if old and new prefix are the same
    if args.old_prefix == args.new_prefix:
        print(f"✗ Error: Old prefix and new prefix are identical: '{args.old_prefix}'")
        print(f"  Nothing to rename.")
        sys.exit(1)
    
    # Print header
    print("\n" + "="*60)
    print("POAFF OUTPUT FILES RENAMER")
    print("="*60)
    
    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No files will be modified")
    
    print(f"\nConfiguration:")
    print(f"  Old prefix: {args.old_prefix}{SEPARATOR}")
    print(f"  New prefix: {args.new_prefix}{SEPARATOR}")
    print(f"  Directory:  {base_path}")
    
    # Process files
    renamer.process_files()
    
    # Print summary
    renamer.print_summary()
    
    # Exit with appropriate code
    if renamer.failed_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
