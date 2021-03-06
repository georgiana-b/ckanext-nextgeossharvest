# -*- coding: utf-8 -*-

from ckanext.harvest.harvesters.base import HarvesterBase
import logging
from string import Template

from bs4 import BeautifulSoup as Soup


log = logging.getLogger(__name__)


class OLUHarvester(HarvesterBase):

    def _normalize_names(self, item_node):
        """
        Return a dictionary of metadata fields with normalized names.

        The Sentinel entries are composed of metadata elements with names
        corresponding to the contents of name_elements and title, link,
        etc. elements. We can just extract all the metadata elements at
        once and rename them in one go.

        Note that elements like `ingestiondate`, which are included in the
        scihub results, will not be added to item as they are not part of the
        list of elements added in the original version.
        """
        spatial_dict = {'gmd:westboundlongitude': None,
                        'gmd:eastboundlongitude': None,
                        'gmd:southboundlatitude': None,
                        'gmd:northboundlatitude': None}

        # Since Micka Catalogue datasets refer to an entire day,
        # there is only one datastamp. Thus, this value will be
        # added to both StartTime and StopTime, and later pos-processed
        normalized_names = {
            'gmd:datestamp': 'StartTime',
            'gmd:westboundlongitude': 'spatial',
            'gmd:eastboundlongitude': 'spatial',
            'gmd:southboundlatitude': 'spatial',
            'gmd:northboundlatitude': 'spatial',
            'gmd:fileidentifier': 'identifier',
            'gmd:title': 'title',
            'gmd:abstract': 'notes',
            'gmd:parentidentifier': 'parent_identifier'
        }
        item = {'spatial': spatial_dict}

        for subitem_node in item_node.findChildren():
            if subitem_node.name in normalized_names:
                key = normalized_names[subitem_node.name]
                if key:
                    if key is 'spatial':
                        item[key][subitem_node.name] = subitem_node.text
                    elif key in ['identifier', 'notes', 'title']:
                        item[key] = subitem_node.text
                    else:
                        item[key] = subitem_node.text.lower()

        # Since the spatial field is composed by 4 values,
        # if either of the values is None, then the whole field is dismissed
        for key in item['spatial']:
            if item['spatial'][key] is None:
                del item['spatial']
                break

        if ('StartTime' in item) and ('StopTime' not in item):
            item['StopTime'] = item['StartTime']

            if not item['StartTime'].endswith('Z'):
                item['StartTime'] += 'T00:00:00.000Z'
                item['StopTime'] += 'T23:59:59.999Z'

        return item

    def _add_collection(self, item):
        """Return the item with collection ID, name, and description."""
        identifier = item['identifier'].lower()
        if identifier.startswith('olu'):
            item['collection_name'] = 'Open Land Use Map'  # noqa: E501
            item['collection_description'] = 'The main idea is to put Open Land Use dataset and also its metadata (from micka.lesprojekt.cz) in RDF format into Virtuoso and explore SPARQL queries that would combine data with metadata. For instance: Show me the datasets (municipalities) where more than 50% of the area is covered by residential areas and data were collected not later than 5 years ago? This query combines some metadata (such as year of data collection and municipality which data covers) with data itself  (object features with residential land use). For automatization of such queries it is necessary to have both data and metadata available for querying and interconnected. In ideal case the output will be endpoint where it will be possible to query both OLU data and metadata, some model queries and possibly some visualization of query results.'  # noqa: E501
            item['collection_id'] = 'OPEN_LAND_USE_MAP'

        return item

    def _get_tags_for_dataset(self, item):
        """Creates a list of tag dictionaries based on a product's metadata."""
        identifier = item['identifier'].lower()
        if identifier.startswith('olu'):
            tags = [{'name': 'OLU'}, {'name': 'open land use'},
                    {'name': 'LULC'}, {'name': 'land use'},
                    {'name': 'land cover'}, {'name': 'agriculture'}]

        else:
            tags = []
            log.debug('No tags for {}'.format(identifier))

        return tags

    def _parse_content(self, content):
        """
        Parse the entry content and return a dictionary using our standard
        metadata terms.
        """
        soup = Soup(content, 'lxml')

        # Create an item dictionary and add metadata with normalized names.
        item = self._normalize_names(soup)

        # If there's a spatial element, convert it to GeoJSON
        # Remove it if it's invalid
        spatial_data = item.pop('spatial', None)
        if spatial_data:
            template = Template('''{"type": "Polygon", "coordinates": [$coords_list]}''')  # noqa: E501
            coords_NW = [float(spatial_data['gmd:westboundlongitude']), float(spatial_data['gmd:northboundlatitude'])]  # noqa: E501
            coords_NE = [float(spatial_data['gmd:eastboundlongitude']), float(spatial_data['gmd:northboundlatitude'])]  # noqa: E501
            coords_SE = [float(spatial_data['gmd:eastboundlongitude']), float(spatial_data['gmd:southboundlatitude'])]  # noqa: E501
            coords_SW = [float(spatial_data['gmd:westboundlongitude']), float(spatial_data['gmd:southboundlatitude'])]  # noqa: E501
            coords_list = [coords_NW, coords_NE, coords_SE, coords_SW, coords_NW]  # noqa: E501

            geojson = template.substitute(coords_list=coords_list)
            item['spatial'] = geojson

        if 'identifier' in item:
            item['identifier'] = item['identifier'].replace('.', '_')
            item['Filename'] = item['identifier'].lower()

        if 'parent_identifier' in item:
            item['parent_identifier'] = item['parent_identifier'].replace('.', '_')  # noqa: E501

        item['name'] = item['identifier'].lower()

        # Thumbnail, alternative and enclosure
        quick_look = soup.find('gmd:md_browsegraphic')

        if quick_look:
            item['thumbnail'] = quick_look.find('gmd:filename').text

        resources_list = soup.find_all({'gmd:online'})
        for resource in resources_list:
            name = resource.find('gmd:name').text.replace(' ', '_')
            if 'GeoJSON' in name:
                item['geojsonLink'] = resource.find('gmd:linkage').text
            elif 'SHP' in name:
                item['shapefileLink'] = resource.find('gmd:linkage').text
            elif 'WMS' in name:
                pass
            else:
                pass

        # Add the collection info
        item = self._add_collection(item)

        item['title'] = item['collection_name']

        item['notes'] = item['collection_description']

        item['tags'] = self._get_tags_for_dataset(item)

        return item

    def _make_geojson_resource(self, item):
        """
        Return a geojson resource dictionary
        """
        if item.get('geojsonLink'):
            name = 'GeoJSON Download from Plan4All'
            description = 'Download the geojson file from Plan4All.'  # noqa: E501
            url = item['geojsonLink']
            order = 1
            _type = 'plan4all_geojson'

            geojson = {'name': name,
                       'description': description,
                       'url': url,
                       'format': 'JSON',
                       'mimetype': 'application/json',
                       'resource_type': _type,
                       'order': order}

            return geojson
        else:
            return None

    def _make_shapefile_resource(self, item):
        """
        Return a shapefile resource dictionary depending on the harvest source.
        """
        if item.get('shapefileLink'):
            name = 'ShapeFile Download from Plan4All'
            description = 'Download ESRI shapefile as zip from Plan4All.'  # noqa: E501
            url = item['shapefileLink']
            order = 2
            _type = 'plan4all_shapefile'

            shapefile = {'name': name,
                         'description': description,
                         'url': url,
                         'format': 'ZIP',
                         'mimetype': 'application/zip',
                         'resource_type': _type,
                         'order': order}

            return shapefile
        else:
            return None

    def _make_thumbnail_resource(self, item):
        """
        Return a thumbnail resource dictionary
        """
        if item.get('thumbnail'):
            name = 'Thumbnail Download'
            description = 'Download a PNG quicklook.'  # noqa: E501
            url = item['thumbnail']
            order = 3
            _type = 'thumbnail'

        else:
            return None

        thumbnail = {'name': name,
                     'description': description,
                     'url': url,
                     'format': 'PNG',
                     'mimetype': 'image/png',
                     'resource_type': _type,
                     'order': order}

        return thumbnail

    def _get_resources(self, parsed_content):
        """Return a list of resource dicts."""
        if self.obj.package and self.obj.package.resources:
            old_resources = [x.as_dict() for x in self.obj.package.resources]
        else:
            old_resources = None

        shapefile = self._make_shapefile_resource(parsed_content)
        geojson = self._make_geojson_resource(parsed_content)
        thumbnail = self._make_thumbnail_resource(parsed_content)

        new_resources = [x for x in [shapefile, geojson, thumbnail] if x]
        if not old_resources:
            resources = new_resources
        else:
            # Replace existing resources or add new ones
            new_resource_types = {x['resource_type'] for x in new_resources}
            resources = []
            for old in old_resources:
                old_type = old.get('resource_type')
                order = old.get('order')
                if old_type not in new_resource_types and order:
                    resources.append(old)
            resources += new_resources

            resources.sort(key=lambda x: x['order'])

        return resources
