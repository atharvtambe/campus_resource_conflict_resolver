from django.core.management.base import BaseCommand
from resources.models import Resource, ResourceType


class Command(BaseCommand):
    help = "Seeds initial campus resources for development and testing."

    def handle(self, *args, **options):
        initial_resources = [
            {
                "name": "Seminar Hall A",
                "resource_type": ResourceType.SEMINAR_HALL,
                "location": "Main Block, 2nd Floor",
                "capacity": 150,
                "description": "Equipped with dual projectors, podium mic, surround sound system, and AC.",
                "is_active": True,
            },
            {
                "name": "Seminar Hall B",
                "resource_type": ResourceType.SEMINAR_HALL,
                "location": "Admin Block, Ground Floor",
                "capacity": 100,
                "description": "Equipped with interactive smartboard and conferencing camera.",
                "is_active": True,
            },
            {
                "name": "Advanced Computing Lab 101",
                "resource_type": ResourceType.LAB,
                "location": "Tech Wing, 1st Floor",
                "capacity": 45,
                "description": "45 high-end Linux workstations with GPU support.",
                "is_active": True,
            },
            {
                "name": "Electronics & IoT Lab 204",
                "resource_type": ResourceType.LAB,
                "location": "Engineering Block, 2nd Floor",
                "capacity": 30,
                "description": "Oscilloscopes, microcontrollers, soldering stations, and test benches.",
                "is_active": True,
            },
            {
                "name": "Lecture Hall 12",
                "resource_type": ResourceType.CLASSROOM,
                "location": "Academic Complex, 3rd Floor",
                "capacity": 80,
                "description": "Stepped lecture hall with ceiling projector and wireless mic.",
                "is_active": True,
            },
            {
                "name": "Epson Portable HD Projector #1",
                "resource_type": ResourceType.PROJECTOR,
                "location": "AV Department, Room 05",
                "capacity": 1,
                "description": "1080p HDMI/Wireless casting projector for external presentations.",
                "is_active": True,
            },
            {
                "name": "Conference Sound Kit A",
                "resource_type": ResourceType.EQUIPMENT,
                "location": "Media Center",
                "capacity": 1,
                "description": "Two collar mics, mixer, amplifier, and wireless receiver.",
                "is_active": True,
            },
            {
                "name": "Old Chemistry Lab (Under Renovation)",
                "resource_type": ResourceType.LAB,
                "location": "Science Wing, Ground Floor",
                "capacity": 25,
                "description": "Currently closed for pipeline maintenance and safety upgrades.",
                "is_active": False,
            },
        ]

        created_count = 0
        for r_data in initial_resources:
            obj, created = Resource.objects.get_or_create(
                name=r_data["name"],
                defaults=r_data
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"Created resource: {obj.name}"))
            else:
                self.stdout.write(f"Resource already exists: {obj.name}")

        self.stdout.write(self.style.SUCCESS(f"Done! Seeded {created_count} new resources."))
