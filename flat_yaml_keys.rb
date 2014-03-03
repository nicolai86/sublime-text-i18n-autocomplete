#/usr/bin/env ruby
require "yaml"

class FlattenYaml
  attr_reader :keys
  def initialize
    @keys = []
  end

  def merge file
    yaml = YAML.load_file file
    @keys |= construct_keys(yaml.values[0])
  end

  def to_json
    @keys
  end

  def find_yaml_files path, depth = 0
    path_suffix = "*/" * depth
    Dir[path + "/#{path_suffix}*.yml"].each do |dir|
      self.merge(dir)
    end

    find_yaml_files(path, depth + 1) if depth < 3
  end

  protected

  def construct_keys yaml

    yaml.inject([]) do |keys, (key, value)|
      if value.is_a? Hash
        keys |= construct_keys(value).map { |child| "#{key}.#{child}" }
      else
        keys << "#{key}"
      end
    end
  end
end

flattener = FlattenYaml.new
flattener.find_yaml_files(ARGV[0])
$stdout << flattener.to_json