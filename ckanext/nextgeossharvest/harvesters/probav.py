# -*- coding: utf-8 -*-
from enum import Enum
import logging
import json
import uuid
from datetime import datetime

from bs4 import BeautifulSoup

from sqlalchemy import desc

from ckan.common import config
from ckan.model import Session
from ckan.plugins.core import implements

from ckanext.harvest.model import HarvestObject
from ckanext.harvest.interfaces import IHarvester

from ckanext.nextgeossharvest.lib.opensearch_base import OpenSearchHarvester
from ckanext.nextgeossharvest.lib.nextgeoss_base import NextGEOSSHarvester

COLLECTION_TEMPLATE = 'PROBAV_{type}_{resolution}_V001'
COLLECTIONS = [
    "PROBAV_L2A_100M_V001"
    "PROBAV_L2A_1KM_V001",
    "PROBAV_L2A_333M_V001",
    "PROBAV_P_V001",
    "PROBAV_S1-TOA_100M_V001",
    "PROBAV_S1-TOA_1KM_V001",
    "PROBAV_S1-TOA_333M_V001",
    "PROBAV_S1-TOC_100M_V001",
    "PROBAV_S1-TOC_1KM_V001",
    "PROBAV_S1-TOC_333M_V001",
    "PROBAV_S1-TOC-NDVI_100M_V001",
    "PROBAV_S10-TOC_1KM_V001",
    "PROBAV_S10-TOC_333M_V001",
    "PROBAV_S10-TOC-NDVI_1KM_V001",
    "PROBAV_S10-TOC-NDVI_333M_V001",
    "PROBAV_S5-TOA_100M_V001",
    "PROBAV_S5-TOC_100M_V001",
    "PROBAV_S5-TOC-NDVI_100M_V001",
    ]

class Units(Enum):
    METERS = 'M'
    KILOMETERS = 'K'

class ProductType(Enum):
    TOC = 'TOA'
    TOC = 'TOC'
    L2A = 'L2A'

class Resolution(object):

    def __init__(self, value, units):
        self.value = value
        self.units = units

class ProbaVCollection(object):

    def __init__(self, product_type, resolution):
        self.product_type = product_type
        self.resolution = resolution

class SProbaVCollection(ProbaVCollection):

    def __init__(self, frequency, product_type, resolution, ndvi):
        super(SProbaVCollection, self).__init__(product_type, resolution)
        self.frequency = frequency
        self.ndvi = ndvi
    
        

class PROBAVHarvester(OpenSearchHarvester, NextGEOSSHarvester):
    """
    A an example of how to build a harvester for OpenSearch sources.

    You'll want to add some custom code (or preferably a custom class) to
    handle parsing the entries themselves, as well as any special logic
    for deciding which entries to import, etc.
    """
    implements(IHarvester)

    def info(self):
        return {
            'name': 'proba-v',
            'title': 'Proba-V Harvester',
            'description': 'A Harvester for Proba-V Products'
            }

    def validate_config(self, config):
        if not config:
            return config

        try:
            config_obj = json.loads(config)

            # If your harvester has a config,
            # validate it here.

        except ValueError as e:
            raise e

        return config

    def gather_stage(self, harvest_job):
        log = logging.getLogger(__name__ + '.{your_harvester}.gather')
        log.debug('{your_harvester} gather_stage for job: %r', harvest_job)

        # Save a reference so you don't need to pass harvest_job to all the
        # methods that might need it. The OpenSearchHarvester class assumes
        # you've done this; you can also use it in your own custom class
        # if you need more complex result parsing logic. This reference only
        # lasts during the gather stage. It won't be available during the other
        # stages.
        self.job = harvest_job

        # Creates self.source_config, value either a dict of config key-value
        # pairs or None
        self._set_source_config(self.job.source.config)

        # What comes next just shows what attributes are required to use the
        # OpenSearchHarvester to gather results.

        # This next section is a bit unwieldy, but allows us to configure
        # how the OpenSearchHarvester parses the results without having to
        # write a separate parser just for the gather stage. If you're
        # harvesting from an OpenSearch source, then you don't need to fully
        # parse each entry during the gather stage. You just need to parse
        # enough to create a harvest object and then store the content of the
        # entry in the harvest object's content field. The real parsing will
        # happen in the import_stage, and that's when you'll use your custom
        # harvester base class.

        # Required: specify the name of the entry element that you'll use as
        # the name or id of the dataset you'll create later. This is used to
        # check if there already is a dataset with that name (to prevent
        # duplicats and enable updates)
        self.os_id_name = 'atom:id' #  Example
        # Required: specify the attribute or attributes of the entry element
        # above in case there is more than one element with the name reference
        # above. Must be a dict. Keys are the attribute names, values are the
        # attribute values. If no attributes are necessary for identifying the
        # element, use {'key': None}.
        self.os_id_attr = {'key': None}  # Example
        # Optional: specify a function or method that will modify the text of
        # the element. For instance, if the text is `urn:uri:the_relevant_part`,
        # you can reference a function here that will return `the_relevant_part`
        # when OpenSearchHarvester processes the entry.
        #self.os_id_mod = None

        # Required: specify the name of the entry element that you'll use as
        # the GUID for the harvest object. Could be the same as os_id_name.
        self.os_guid_name = 'atom:id'  # Example
        # Required: specify the attribute or attributes of the entry element
        # above in case there is more than one element with the name reference
        # above. Must be a dict. Keys are the attribute names, values are the
        # attribute values. If no attributes are necessary for identifying the
        # element, use {'key': None}. Could be the same as os_id_attr.
        self.os_guid_attr = {'key': None}  # Example
        # Optional: specify a function or method that will modify the text of
        # the element. For instance, if the text is `urn:uri:the_relevant_part`,
        # you can reference a function here that will return `the_relevant_part`
        # when OpenSearchHarvester processes the entry. Could be the same as
        # os_id_mod.
        #self.os_guid_mod = None

        # The following three attributes are also required. They work like their
        # siblings described above. The restart date is the date that will be
        # used for creating new queries if the harvester has to restart. It
        # will be the lower bound of the temporal part of the query.
        # The restart date of the last harvest object that was successfully
        # imported will be the new start date.
        self.os_restart_date_name = 'atom:updated'
        self.os_restart_date_attr = {'key': None}
        # self.os_restart_mod = None

        # Optional, and probably only need in cases like the triple Sentinel
        # harvester. The flagged extra is the name of an extra field to check
        # before deciding that a dataset really should not be updated when
        # the update_all setting is False. If flagged_extra is None, the
        # harvester will not update datasets that already exist. If
        # flagged_extra is the name of an extra, the harvester will check to
        # see if it's in the package dictionary. If it's _not_ in the package
        # dictionary, then the harvester _will_ update the dataset. This is
        # useful in the case of the Sentinel harvesters, because it means that
        # each harvester can update datasets created by the other two harvesters
        # and if we need to re-run the harvester, we can control whether it
        # skips datasets it created itself or whether it updates them
        # (for instance, we might re-run the harvester to grab products that
        # were skipped, and we wouldn't want to update all the old datasets—
        # but we also might re-run it to update the metadata if we change the
        # way it's represented, in which case we would want to update all the
        # old products.)
        self.flagged_extra = None

        harvest_url = 'http://www.vito-eodata.be/openSearch/findProducts.atom?collection=urn:ogc:def:EOP:VITO:PROBAV_L2A_333M_V001&platform=PV01&start=2018-01-01&end=2018-01-02&count=500'# This will be the URL that you'll begin harvesting from
        # when the gather stage begins. How you construct it is up to you,
        # but it needs to be a valid URL that includes the OpenSearch query.
        log.debug('Harvest URL is {}'.format(harvest_url))


        # The _crawl_results() method belongs to the OpenSearchHarvester class.
        # harvest_url is the only required argument. limit, timeout, username,
        # and password are all optional and default to 100, 5, None and None,
        # respectively.

        # If you're going to create the new harvester jobs on a rolling basis
        # via cron jobs, you don't need to grab all the results from a date
        # range at once. The harvester will resume from the point it stopped
        # each time it runs. You can control how many OpenSearch entries are
        # gathered by using the limit argument.

        # Optioninal snippet if you want to log source repsonses like the
        # Sentinel harvester do.
        if not hasattr(self, 'provider_logger'):
            self.provider_logger = self.make_provider_logger()
        self.provider = '' # a string indicating the source to be used in the logs
        # (could be set in the config)
        # As explained above, only harvest_url is required.
        ids = self._crawl_results(harvest_url, timeout=60, parser='lxml-xml')
        
        print(ids)

        return ids

    def fetch_stage(self, harvest_object):
        """Fetch was completed during gather."""

        # We don't need to fetch anything—the OpenSearch entries contain all
        # the content we need for the import stage.

        return True
    
    def _parse_content(self, content_str):
        content = BeautifulSoup(content_str, 'lxml-xml')
        collection = self._parse_collection(content)
        parsed_content = {}
        parsed_content['title']  = self._get_title(collection)
        parsed_content['description'] = self._get_description(collection)
        parsed_content['tags'] = self._get_tags(collection)
        parsed_content['identifier'] = self._parse_identifier(content)
        parsed_content['uuid'] = str(uuid.uuid4())
        parsed_content['StartTime'], parsed_content['StopTime'] = self._parse_data(content)
        parsed_content['Collection'] = collection
        parsed_content['name'] = self._parse_name(content)
        parsed_content['spatial'] = self._bbox_to_geojson(self._parse_bbox(content))
        return parsed_content

    
    def _parse_collection(self, content):
        identifier = content.identifier
        return self._parse_collection_from_identifier(identifier)
    
    def _parse_collection_from_identifier(self, identifier):
        collection_name = identifier.split(':')[5]
        _, product_type, resolution_str, _ = collection_name.split('_')
        resolution = self._parse_resolution(resolution_str) 
        if product_type == ProductType.L2A:
            return ProbaVCollection(ProductType.L2A, resolution)
        else:
            product_parts = product_type.split('-')
            frequency = int(product_parts[0][1:])
            subtype = ProductType(product_parts[1])
            ndvi = len(product_parts) > 0 and product_parts[2] == 'NDVI'
            return SProbaVCollection(frequency, subtype, resolution, ndvi)
    
    def _parse_resolution(self, resolution_str):
        #we are assuming resolution is one of {100M, 1Km, 333M}
        if resolution_str.endswith('KM'):
            units = Units.KILOMETERS
            value = int(resolution_str[:-2])
        else:
            units = Units.METERS
            value = int(resolution_str[:-1])
        return Resolution(value, units)
        
    def _get_resources(self, content):
        return []